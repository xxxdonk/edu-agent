from __future__ import annotations

import re

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent
from .drafts import ReadingDraft


class ReadingAgent(BaseResourceAgent):
    agent_name = "reading_agent"
    resource_type = ResourceType.READING

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
            "你是一位机器学习课程研究助理。只依据提供的课程知识库生成简洁拓展阅读。"
            "私有输出固定为 overview、core_points、practice_connection、further_study。"
            "overview 是一个概览段落；core_points 必须恰好包含三个完整要点；"
            "practice_connection 说明如何联系实践；further_study 说明下一步学习方向。"
            "不要输出 Markdown 标题、资源元数据、来源字段、外部 URL，"
            "也不要虚构论文、统计数据或知识库未提供的事实。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"学习历史：{context.profile.learning_history.value}\n"
            f"学习目标：{context.profile.learning_goals.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请严格按私有 JSON schema 返回四部分简单段落结构。"
        messages = [LLMMessage(role="user", content=user_content)]

        return await self._generate_with_one_format_repair(
            system_prompt=system_prompt,
            messages=messages,
            response_model=ReadingDraft,
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
        draft = ReadingDraft(
            overview=(
                f"{topic}需要结合概念定义、数学表达和算法流程理解。"
                "阅读时应以课程知识库列出的章节为依据，先建立整体框架，再核对细节。"
            ),
            core_points=[
                f"明确{topic}要解决的问题，以及输入、输出和目标函数之间的关系。",
                f"沿课程章节梳理{topic}的关键步骤，并解释每一步为什么必要。",
                f"结合示例比较正确用法与常见误区，记录仍需要验证的疑问。",
            ],
            practice_connection=(
                f"在分类项目中选取一个小数据集，标注{topic}对应的处理步骤，"
                "并用训练与验证结果检查自己的理解。"
            ),
            further_study=(
                "完成本节后，继续阅读来源列表中的相邻课程章节，"
                "把当前主题与前置数学知识、模型评估和项目实践连接起来。"
            ),
        )
        return self._finalize_draft(
            draft,
            topic,
            difficulty,
            references,
            context,
        )

    def _finalize_draft(
        self,
        draft: ReadingDraft,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        overview = self._normalize_paragraph(draft.overview)
        core_points = [
            self._normalize_list_item(point) for point in draft.core_points
        ]
        practice = self._normalize_paragraph(draft.practice_connection)
        further_study = self._normalize_paragraph(draft.further_study)
        content = "\n".join(
            [
                f"# {topic} 拓展阅读",
                "",
                "## 概览",
                overview,
                "",
                "## 三个核心要点",
                *[f"- {point}" for point in core_points],
                "",
                "## 实践联系",
                practice,
                "",
                "## 后续学习",
                further_study,
                "",
            ]
        )
        return Resource(
            resource_id=self._make_resource_id(),
            resource_type=ResourceType.READING,
            title=f"{topic} 拓展阅读材料",
            content=content,
            content_format="markdown",
            target_topic=topic,
            difficulty=Difficulty(difficulty),
            personalization_reason=self._personalization_reason(context),
            source_references=references,
            review_status="pending",
        )

    @staticmethod
    def _normalize_paragraph(content: str) -> str:
        return " ".join(part.strip() for part in content.splitlines() if part.strip())

    @classmethod
    def _normalize_list_item(cls, content: str) -> str:
        normalized = cls._normalize_paragraph(content)
        return re.sub(r"^(?:[-*+]\s+|\d+[.)、]\s*)", "", normalized)
