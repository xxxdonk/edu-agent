from __future__ import annotations

import re

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent, ResourceDraftFormatError
from .drafts import MindMapDraft


class MindMapAgent(BaseResourceAgent):
    agent_name = "mind_map_agent"
    resource_type = ResourceType.MIND_MAP

    async def _generate_with_llm(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        system_prompt = (
            "你是一位机器学习知识图谱专家。只依据课程知识库生成 Mermaid mindmap。"
            "私有输出只有 content 一个字段；content 的第一行必须是 mindmap，"
            "后续只包含一个主题根节点及分层子节点。"
            "content 中不要包含 Markdown 代码围栏、解释文字、HTML 或来源元数据。"
            "使用 12 至 24 个简短中文节点，最多四层。必须覆盖核心定义、前置知识、"
            "原理、流程、常见错误、项目应用和 Evaluation 重点。"
            "节点不得使用引号、冒号、反斜杠、复杂公式或未转义括号，"
            "节点内容必须能够由课程知识库支持。"
        )
        user_content = f"主题：{topic}\n难度：{difficulty}\n"
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请只在私有 JSON 的 content 字段中返回 Mermaid mindmap 正文。"
        messages = [LLMMessage(role="user", content=user_content)]

        return await self._generate_with_one_format_repair(
            system_prompt=system_prompt,
            messages=messages,
            response_model=MindMapDraft,
            finalize=lambda draft: self._finalize_draft(
                draft,
                topic,
                difficulty,
                references,
                context,
            ),
        )

    def _generate_heuristic(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        level_labels = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}
        label = level_labels.get(difficulty, "入门")
        content = (
            "mindmap\n"
            f"  root(({topic} {label}))\n"
            "    核心定义\n"
            "      任务目标\n"
            "      输入输出\n"
            "    前置知识\n"
            "      数据划分\n"
            "      损失函数\n"
            "    核心原理\n"
            "      参数学习\n"
            "      泛化验证\n"
            "    执行流程\n"
            "      建立基线\n"
            "      训练模型\n"
            "      验证调整\n"
            "    常见错误\n"
            "      数据泄漏\n"
            "      盲目调参\n"
            "    项目应用\n"
            "      客户流失\n"
            "      模型比较\n"
            "    Evaluation重点\n"
            "      结果解释\n"
            "      错题复盘\n"
        )
        return self._finalize_draft(
            MindMapDraft(content=content),
            topic,
            difficulty,
            references,
            context,
        )

    def _finalize_draft(
        self,
        draft: MindMapDraft,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        return Resource(
            resource_id=self._make_resource_id(),
            resource_type=ResourceType.MIND_MAP,
            title=f"{topic} 思维导图",
            content=self._normalize_mermaid(draft.content),
            content_format="mermaid",
            target_topic=topic,
            difficulty=Difficulty(difficulty),
            personalization_reason=self._personalization_reason(context),
            source_references=references,
            review_status="pending",
        )

    @staticmethod
    def _normalize_mermaid(content: str) -> str:
        cleaned = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
        fenced = re.fullmatch(
            r"```(?:mermaid)?\s*(.*?)\s*```",
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            cleaned = fenced.group(1).strip()

        lines = cleaned.splitlines()
        if lines and lines[0].strip().casefold() == "mermaid":
            lines = lines[1:]
        if not lines or lines[0].strip().casefold() != "mindmap":
            raise ResourceDraftFormatError(
                "mind map content must start with Mermaid mindmap"
            )
        lines[0] = "mindmap"
        if not any(line.strip() and not line.lstrip().startswith("%%") for line in lines[1:]):
            raise ResourceDraftFormatError("mind map content must include a root node")

        normalized = "\n".join(lines)
        brackets = {"{": "}", "[": "]", "(": ")"}
        stack: list[str] = []
        for character in normalized:
            if character in brackets:
                stack.append(brackets[character])
            elif character in brackets.values():
                if not stack or stack.pop() != character:
                    raise ResourceDraftFormatError("mind map brackets are not balanced")
        if stack:
            raise ResourceDraftFormatError("mind map brackets are not balanced")
        return normalized + "\n"
