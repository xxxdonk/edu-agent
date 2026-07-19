from __future__ import annotations

import ast
import difflib
import json
import logging
import re
import textwrap

from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType
from app.guardrails.checker import GuardrailChecker

logger = logging.getLogger(__name__)


class ReviewerAgent:
    agent_name = "reviewer_agent"

    async def review(
        self,
        resource: Resource,
        context: SharedAgentContext,
    ) -> Resource:
        issues: list[str] = []

        # 原有 5 项检查
        self._check_source_references(resource, issues)
        self._check_difficulty_match(resource, context, issues)
        self._check_personalization(resource, context, issues)
        self._check_content_integrity(resource, issues)
        self._check_placeholders(resource, issues)
        self._check_resource_type_format(resource, issues)

        # 新增 4 项检查
        self._check_verifiability(resource, issues)
        self._check_mermaid_validity(resource, issues)
        self._check_code_executability(resource, issues)
        self._check_quiz_consistency(resource, issues)
        self._check_resource_quality(resource, issues)

        # Guardrail 检查
        guardrail_ok, guardrail_issues = GuardrailChecker.check(resource)
        if not guardrail_ok:
            issues.extend(guardrail_issues)

        # 评分仅进入安全日志，不改变公共 Resource Schema。
        source_coverage = self._compute_source_coverage(resource)
        personalization_score = self._compute_personalization_score(resource, context)
        factuality_score = self._compute_factuality_score(resource)
        logger.debug(
            "review_scores resource_id=%s source_coverage=%.2f personalization=%.2f factuality=%.2f",
            resource.resource_id,
            source_coverage,
            personalization_score,
            factuality_score,
        )

        # 确定状态
        if guardrail_issues:
            status = "rejected"
        elif issues:
            status = "needs_revision"
        else:
            status = "approved"

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
            )

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
            )

        return resource.model_copy(update={"review_status": "approved"})

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
    def _check_placeholders(resource: Resource, issues: list[str]) -> None:
        placeholder_patterns = (
            "待补充",
            "在此处实现",
            "选项一（正确描述）",
            "……",
        )
        matched = [pattern for pattern in placeholder_patterns if pattern in resource.content]
        lowered = resource.content.casefold()
        if (
            resource.resource_type != ResourceType.CODING
            and re.search(r"\b(?:todo|tbd|fixme)\b", lowered)
        ):
            matched.append("TODO/TBD/FIXME")
        if matched:
            issues.append(f"内容包含占位符：{'、'.join(dict.fromkeys(matched))}")

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
                # Markdown renderers commonly indent an entire fenced block.
                # Remove only that shared presentation indentation; genuine
                # relative-indentation and syntax errors remain detectable.
                ast.parse(textwrap.dedent(code))
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
        if resource.content_format == "json":
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                issues.append("Quiz JSON 无法解析")
                return
            questions = payload.get("questions") if isinstance(payload, dict) else None
            if not isinstance(questions, list) or not questions:
                issues.append("Quiz JSON 缺少非空 questions 数组")
                return
            if not 8 <= len(questions) <= 12:
                issues.append("Quiz 题目数量应为 8 至 12 题")
            normalized_questions: set[str] = set()
            levels: set[str] = set()
            for index, question in enumerate(questions, start=1):
                if not isinstance(question, dict):
                    issues.append(f"Quiz 第 {index} 题不是对象")
                    continue
                missing = [
                    field
                    for field in ("question", "answer", "explanation")
                    if not str(question.get(field, "")).strip()
                ]
                if missing:
                    issues.append(
                        f"Quiz 第 {index} 题缺少必要字段：{'、'.join(missing)}"
                    )
                normalized = re.sub(
                    r"[\W_]+", "", str(question.get("question", "")).casefold()
                )
                if normalized in normalized_questions:
                    issues.append(f"Quiz 第 {index} 题与前面题目重复")
                normalized_questions.add(normalized)
                levels.add(str(question.get("level", "")).strip())
                if question.get("type") == "single_choice":
                    options = question.get("options")
                    if not isinstance(options, list) or len(options) < 2:
                        issues.append(f"Quiz 第 {index} 题缺少有效选项")
                    else:
                        answer = str(question.get("answer", "")).strip().upper()
                        option_labels = {
                            str(option).strip().split(".", maxsplit=1)[0].upper()
                            for option in options
                            if str(option).strip()
                        }
                        if answer and answer not in option_labels:
                            issues.append(f"Quiz 第 {index} 题答案不在选项中")
                        if len({str(option).strip() for option in options}) != len(options):
                            issues.append(f"Quiz 第 {index} 题存在重复选项")
            if not {"basic", "intermediate", "advanced"} <= levels:
                issues.append("Quiz 未完整覆盖基础、进阶和挑战三个层次")
            return

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

    @classmethod
    def _check_resource_quality(cls, resource: Resource, issues: list[str]) -> None:
        if resource.resource_type == ResourceType.EXPLANATION:
            cls._check_explanation_quality(resource, issues)
        elif resource.resource_type == ResourceType.MIND_MAP:
            cls._check_mind_map_quality(resource, issues)
        elif resource.resource_type == ResourceType.READING:
            cls._check_reading_quality(resource, issues)
        elif resource.resource_type == ResourceType.CODING:
            cls._check_coding_quality(resource, issues)

    @staticmethod
    def _missing_sections(content: str, labels: tuple[str, ...]) -> list[str]:
        return [label for label in labels if label not in content]

    @classmethod
    def _check_explanation_quality(
        cls, resource: Resource, issues: list[str]
    ) -> None:
        required = (
            "学习目标", "为什么需要学习", "前置知识", "核心概念", "原理与公式",
            "分步", "完整示例", "常见错误", "快速自检", "FAQ", "本节总结", "下一步",
        )
        missing = cls._missing_sections(resource.content, required)
        if missing:
            issues.append(f"课程讲解缺少结构：{'、'.join(missing)}")
        if resource.content.count("**Q") < 5:
            issues.append("课程讲解 FAQ 少于 5 组")
        if resource.content.count("常见错误") < 1 or len(
            re.findall(r"^\d+\. \*\*", resource.content, re.MULTILINE)
        ) < 4:
            issues.append("课程讲解常见错误不足 4 条")
        for opening, closing in ((r"\(", r"\)"), (r"\[", r"\]")):
            if resource.content.count(opening) != resource.content.count(closing):
                issues.append("课程讲解 LaTeX 定界符未闭合")
                break

    @staticmethod
    def _check_mind_map_quality(resource: Resource, issues: list[str]) -> None:
        lines = [
            line for line in resource.content.splitlines()
            if line.strip() and line.strip() != "mindmap" and not line.lstrip().startswith("%%")
        ]
        if not 12 <= len(lines) <= 24:
            issues.append("思维导图节点数量应为 12 至 24 个")
        if any((len(line) - len(line.lstrip(" "))) // 2 > 4 for line in lines):
            issues.append("思维导图层级超过 4 层")
        dangerous = re.compile(r"[\"'`:\\]|<[^>]+>")
        if any(dangerous.search(line.strip()) for line in lines):
            issues.append("思维导图节点包含复杂或危险文本")

    @classmethod
    def _check_reading_quality(cls, resource: Resource, issues: list[str]) -> None:
        required = (
            "阅读目标", "10 分钟快速阅读", "深入阅读", "项目阅读路线",
            "关键术语表", "阅读检查问题", "推荐实践", "真实 RAG 来源",
        )
        missing = cls._missing_sections(resource.content, required)
        if missing:
            issues.append(f"拓展阅读缺少结构：{'、'.join(missing)}")
        glossary_section = resource.content.partition("关键术语表")[2].partition("阅读检查问题")[0]
        if glossary_section.count("\n-") < 8:
            issues.append("拓展阅读术语少于 8 个")

    @classmethod
    def _check_coding_quality(cls, resource: Resource, issues: list[str]) -> None:
        required = (
            "实验目标", "环境说明", "输入数据", "分步骤任务", "完整 Python 代码",
            "预期输出", "TODO 练习", "调试提示", "进阶挑战", "反思问题",
        )
        missing = cls._missing_sections(resource.content, required)
        if missing:
            issues.append(f"代码实践缺少结构：{'、'.join(missing)}")
        if "```python" not in resource.content or resource.content.count("```") < 2:
            issues.append("代码实践缺少完整 Python 代码块")
        dangerous = re.compile(
            r"\b(?:os\.system|subprocess|eval|exec)\s*\(|"
            r"\b(?:remove|unlink|rmtree)\s*\(|(?:[A-Za-z]:\\|/home/|/Users/)"
        )
        if dangerous.search(resource.content):
            issues.append("代码实践包含危险命令或绝对路径")

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

    @staticmethod
    def content_similarity(left: str, right: str) -> float:
        """Return a lightweight normalized similarity score without NLP dependencies."""

        def normalize(value: str) -> str:
            value = re.sub(r"```[\s\S]*?```", "", value)
            value = re.sub(r"^#{1,6}\s+.*$", "", value, flags=re.MULTILINE)
            return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()

        normalized_left = normalize(left)
        normalized_right = normalize(right)
        if not normalized_left or not normalized_right:
            return 0.0
        return difflib.SequenceMatcher(
            None, normalized_left, normalized_right, autojunk=False
        ).ratio()
