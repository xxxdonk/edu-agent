from __future__ import annotations

import logging
import ast

from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType
from app.schemas.common import Difficulty
from app.guardrails.checker import GuardrailChecker

logger = logging.getLogger(__name__)


class ReviewerAgent:
    agent_name = "reviewer_agent"

    async def review(
        self,
        resource: Resource,
        context: SharedAgentContext,
    ) -> tuple[Resource, dict]:
        issues: list[str] = []

        # 原有 5 项检查
        self._check_source_references(resource, issues)
        self._check_difficulty_match(resource, context, issues)
        self._check_personalization(resource, context, issues)
        self._check_content_integrity(resource, issues)
        self._check_resource_type_format(resource, issues)

        # 新增 4 项检查
        self._check_verifiability(resource, issues)
        self._check_mermaid_validity(resource, issues)
        self._check_code_executability(resource, issues)
        self._check_quiz_consistency(resource, issues)

        # Guardrail 检查
        guardrail_ok, guardrail_issues = GuardrailChecker.check(resource)
        if not guardrail_ok:
            issues.extend(guardrail_issues)

        # 计算各项评分
        source_coverage = self._compute_source_coverage(resource)
        personalization_score = self._compute_personalization_score(resource, context)
        factuality_score = self._compute_factuality_score(resource)

        # 确定状态
        if guardrail_issues:
            status = "rejected"
        elif issues:
            status = "needs_revision"
        else:
            status = "approved"

        # 构建修正内容（如有可修复问题）
        corrected_content = self._generate_corrected_content(resource, issues) if issues else None

        review_dict = {
            "status": status,
            "issues": issues,
            "corrected_content": corrected_content,
            "source_coverage": source_coverage,
            "personalization_score": personalization_score,
            "factuality_score": factuality_score,
        }

        if status == "rejected":
            logger.warning("review_rejected resource_id=%s issues=%s", resource.resource_id, guardrail_issues)
            return resource.model_copy(
                update={
                    "review_status": "rejected",
                    "personalization_reason": (
                        resource.personalization_reason
                        + f" [审校拒绝：{'；'.join(guardrail_issues)}]"
                    ),
                }
            ), review_dict

        if status == "needs_revision":
            logger.warning("review_issues resource_id=%s issues=%s", resource.resource_id, issues)
            return resource.model_copy(
                update={
                    "review_status": "needs_revision",
                    "personalization_reason": (
                        resource.personalization_reason
                        + f" [审校问题：{'；'.join(issues)}]"
                    ),
                }
            ), review_dict

        return resource.model_copy(update={"review_status": "approved"}), review_dict

    # ========== 原有 5 项检查 ==========

    @staticmethod
    def _check_source_references(resource: Resource, issues: list[str]) -> None:
        if not resource.source_references:
            issues.append("缺少知识库来源引用")
            return
        for ref in resource.source_references:
            if not ref.source_id or not ref.locator:
                issues.append(f"来源引用不完整：source_id={ref.source_id}")
                return

    @staticmethod
    def _check_difficulty_match(
        resource: Resource,
        context: SharedAgentContext,
        issues: list[str],
    ) -> None:
        profile_level = context.profile.knowledge_level.value
        if profile_level and resource.difficulty.value != profile_level:
            issues.append(
                f"难度不匹配：资源={resource.difficulty.value}，学生水平={profile_level}"
            )

    @staticmethod
    def _check_personalization(
        resource: Resource,
        context: SharedAgentContext,
        issues: list[str],
    ) -> None:
        if len(resource.personalization_reason) < 10:
            issues.append("个性化理由过短，缺乏充分说明")
        weak_topics = context.profile.weak_topics.value or []
        if weak_topics and not any(
            wt.lower() in resource.personalization_reason.lower() for wt in weak_topics
        ):
            issues.append("个性化理由未提及学生薄弱点")

    @staticmethod
    def _check_content_integrity(resource: Resource, issues: list[str]) -> None:
        if len(resource.content) < 50:
            issues.append("内容过短，可能不完整")
        if not resource.title or len(resource.title) < 3:
            issues.append("标题过短或缺失")

    @staticmethod
    def _check_resource_type_format(resource: Resource, issues: list[str]) -> None:
        expected_formats: dict[ResourceType, set[str]] = {
            ResourceType.EXPLANATION: {"markdown", "text"},
            ResourceType.MIND_MAP: {"mermaid"},
            ResourceType.QUIZ: {"json", "markdown"},
            ResourceType.READING: {"markdown", "text"},
            ResourceType.CODING: {"python", "markdown"},
        }
        allowed = expected_formats.get(resource.resource_type, set())
        if resource.content_format not in allowed:
            issues.append(
                f"content_format 不匹配：{resource.resource_type.value} "
                f"期望 {allowed}，实际 {resource.content_format}"
            )

    # ========== 新增 4 项检查 ==========

    @staticmethod
    def _check_verifiability(resource: Resource, issues: list[str]) -> None:
        """检查内容是否存在无法验证的模糊表述"""
        unverifiable_patterns = [
            "最新研究表明", "最新研究发现", "最近有研究显示",
            "有研究表明", "据统计", "据调查",
            "众所周知", "业界公认", "普遍认为",
        ]
        content_lower = resource.content.lower()
        for pattern in unverifiable_patterns:
            if pattern in content_lower:
                issues.append(f"内容包含无法验证的模糊表述：'{pattern}'，请提供具体引用来源")
                return  # 找到一个就记录并返回，避免重复

    @staticmethod
    def _check_mermaid_validity(resource: Resource, issues: list[str]) -> None:
        """对 mind_map 类型资源检查 Mermaid 语法基本有效性"""
        if resource.resource_type != ResourceType.MIND_MAP:
            return

        content = resource.content.strip()

        # 检查是否包含 mindmap 或 graph 关键字
        has_mindmap_keyword = "mindmap" in content.lower()
        has_graph_keyword = "graph" in content.lower()

        if not has_mindmap_keyword and not has_graph_keyword:
            issues.append("Mermaid 内容缺少 'mindmap' 或 'graph' 关键字")
            return

        # 检查根节点存在（非空内容且至少有一行非空）
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if not lines:
            issues.append("Mermaid 内容为空，没有根节点")
            return

        # 检查括号配对：{} [] ()
        brackets = {"{": "}", "[": "]", "(": ")"}
        stack: list[str] = []
        for char in content:
            if char in brackets:
                stack.append(brackets[char])
            elif char in brackets.values():
                if not stack or stack.pop() != char:
                    issues.append(f"Mermaid 括号不匹配：'{char}' 缺少对应的开括号")
                    return
        if stack:
            issues.append("Mermaid 存在未闭合的括号")

    @staticmethod
    def _check_code_executability(resource: Resource, issues: list[str]) -> None:
        """对 coding 类型资源检查 Python 代码是否可语法解析"""
        if resource.resource_type != ResourceType.CODING:
            return

        content = resource.content

        # 提取 ```python ... ``` 代码块
        code_blocks: list[str] = []
        in_block = False
        block_lines: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```python") or stripped.startswith("```py"):
                in_block = True
                block_lines = []
            elif stripped == "```" and in_block:
                in_block = False
                if block_lines:
                    code_blocks.append("\n".join(block_lines))
            elif in_block:
                block_lines.append(line)

        if not code_blocks:
            # 尝试将全部内容作为代码解析
            code_blocks = [content]

        parse_errors = []
        for i, code in enumerate(code_blocks):
            try:
                ast.parse(code)
            except SyntaxError as e:
                parse_errors.append(f"代码块 {i+1} 语法错误：{e.msg} (行 {e.lineno})")

        if parse_errors:
            issues.append(f"Python 代码解析失败：{'；'.join(parse_errors)}")

    @staticmethod
    def _check_quiz_consistency(resource: Resource, issues: list[str]) -> None:
        """对 quiz 类型资源检查题目答案一致性"""
        if resource.resource_type != ResourceType.QUIZ:
            return

        content = resource.content
        content_lower = content.lower()

        # 基本检查：内容中至少需要包含 question / answer / explanation
        checks = {
            "question": "question" in content_lower or "题目" in content,
            "answer": "answer" in content_lower or "答案" in content or "正确" in content,
            "explanation": "explanation" in content_lower or "解析" in content or "解释" in content,
        }

        missing = [k for k, v in checks.items() if not v]
        if missing:
            issues.append(f"Quiz 内容缺少必要字段：{'、'.join(missing)}")

    # ========== 评分计算 ==========

    @staticmethod
    def _compute_source_coverage(resource: Resource) -> float:
        """评估来源覆盖度（0-1）"""
        if not resource.source_references:
            return 0.1  # 完全没有来源给极低分

        valid_refs = [
            ref for ref in resource.source_references
            if ref.source_id and ref.locator
        ]
        if not valid_refs:
            return 0.2

        # 有有效来源引用 + 来源数量作为覆盖度的简单衡量
        ref_count = len(valid_refs)
        if ref_count >= 3:
            return 0.9
        elif ref_count >= 2:
            return 0.7
        else:
            return 0.5

    @staticmethod
    def _compute_personalization_score(
        resource: Resource,
        context: SharedAgentContext,
    ) -> float:
        """评估个性化匹配度（0-1）"""
        score = 0.0

        # 个性化理由长度（0-0.3）
        reason_len = len(resource.personalization_reason)
        if reason_len >= 50:
            score += 0.3
        elif reason_len >= 20:
            score += 0.2
        elif reason_len >= 10:
            score += 0.1

        # 是否提及薄弱点（0-0.3）
        weak_topics = context.profile.weak_topics.value or []
        if weak_topics:
            matched = any(
                wt.lower() in resource.personalization_reason.lower()
                for wt in weak_topics
            )
            if matched:
                score += 0.3
        else:
            score += 0.15  # 没有薄弱点时给部分分

        # 难度匹配（0-0.2）
        try:
            profile_level = context.profile.knowledge_level.value
            if profile_level and resource.difficulty.value == profile_level:
                score += 0.2
            elif profile_level:
                score += 0.05
        except Exception:
            score += 0.1

        # 涉及认知风格或目标（0-0.2）
        cognitive_keywords = ["视觉", "听觉", "动手", "阅读", "抽象", "具体",
                              "visual", "auditory", "kinesthetic", "reading"]
        goal_keywords = ["考试", "面试", "项目", "工作", "竞赛", "兴趣",
                         "exam", "interview", "project", "competition"]
        reason_lower = resource.personalization_reason.lower()
        has_cognitive = any(kw in reason_lower for kw in cognitive_keywords)
        has_goal = any(kw in reason_lower for kw in goal_keywords)
        if has_cognitive:
            score += 0.1
        if has_goal:
            score += 0.1

        return min(score, 1.0)

    @staticmethod
    def _compute_factuality_score(resource: Resource) -> float:
        """评估事实准确性（0-1），基于内容是否可验证"""
        content = resource.content
        score = 1.0

        # 扣分项：模糊表述
        unverifiable_patterns = [
            "最新研究表明", "最新研究发现", "最近有研究显示",
            "有研究表明", "据统计", "据调查",
            "众所周知", "业界公认", "普遍认为",
        ]
        content_lower = content.lower()
        deductions = sum(1 for p in unverifiable_patterns if p in content_lower)
        score -= deductions * 0.08

        # 加分项：有具体数字、公式、引用
        has_numbers = any(c.isdigit() for c in content)
        has_formulas = "$" in content
        has_citations = "[" in content and "]" in content and any(
            k in content_lower for k in ["et al.", "chapter", "出版社", "journal"]
        )

        if has_citations:
            score = min(score + 0.1, 1.0)
        if has_formulas:
            score = min(score + 0.05, 1.0)
        if has_numbers:
            score = min(score + 0.05, 1.0)

        return max(min(score, 1.0), 0.0)

    @staticmethod
    def _generate_corrected_content(resource: Resource, issues: list[str]) -> str | None:
        """生成修正内容建议（简单实现，返回问题标注后的内容）"""
        if not issues:
            return None
        lines = [
            "# 审校修正建议\n",
            "以下为检测到的问题及对应内容区域：\n",
        ]
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. **{issue}**\n")
        lines.append(f"\n---\n\n{resource.content[:500]}{'...' if len(resource.content) > 500 else ''}")
        return "".join(lines)
