from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent


class ExplanationAgent(BaseResourceAgent):
    agent_name = "explanation_agent"
    resource_type = ResourceType.EXPLANATION

    async def _generate_with_llm(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        profile = context.profile
        system_prompt = (
            "你是一位机器学习课程讲师。根据学生画像和课程知识库，"
            "生成一份个性化的课程讲解文档（Markdown 格式）。"
            "必须包含：概念定义、核心原理、直观示例、关键公式和常见误区。"
            "难度与学生的 knowledge_level 匹配。"
        )
        user_content = (
            f"课程主题：{topic}\n"
            f"难度：{difficulty}\n"
            f"学生薄弱点：{profile.weak_topics.value}\n"
            f"认知风格：{profile.cognitive_style.value}\n"
            f"学习目标：{profile.learning_goals.value}\n"
            f"学习历史：{profile.learning_history.value}\n"
        )
        if rag_context:
            user_content += f"\n知识库参考：\n{rag_context}"
        user_content += "\n请生成一份结构清晰的 Markdown 讲解文档。"

        draft = await self._llm_client.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_content)],
            response_model=Resource,
        )
        return self._finalize(draft, topic, difficulty, references, context)

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

        rag_section = ""
        if rag_context:
            rag_section = f"\n## 课程知识库参考\n{rag_context}\n"

        content = (
            f"# {topic} — {label}讲解\n\n"
            f"## 概念定义\n{topic}是机器学习中的核心概念。"
            f"本讲解面向{difficulty}水平学习者，"
            f"采用{context.profile.cognitive_style.value or '综合'}风格编排。\n\n"
            f"## 核心原理\n（本节建议结合课程知识库与实际案例理解）\n\n"
            f"## 直观示例\n以一个简单场景说明{topic}的直观含义：\n"
            f"- 输入是什么\n- 处理过程\n- 输出结果\n\n"
            f"## 关键公式\n`待补充：请参考课程资料中{topic}的数学定义`\n\n"
            f"## 常见误区\n1. 误区一：……\n2. 误区二：……\n\n"
            f"## 学习建议\n"
            f"- 建议配合思维导图梳理{topic}的知识脉络\n"
            f"- 完成相关练习题巩固理解\n"
            f"{rag_section}"
        )
        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} — {label}课程讲解",
                content=content,
                content_format="markdown",
                target_topic=topic,
                difficulty=Difficulty(difficulty),
                personalization_reason=self._personalization_reason(context),
                source_references=references or [],
                review_status="pending",
            ),
            topic, difficulty, references, context,
        )

    def _finalize(
        self,
        draft: Resource,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        return Resource(
            resource_id=draft.resource_id or self._make_resource_id(),
            resource_type=ResourceType.EXPLANATION,
            title=draft.title or f"{topic} 课程讲解",
            content=draft.content,
            content_format="markdown",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
