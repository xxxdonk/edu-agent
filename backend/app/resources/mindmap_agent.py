from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent


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
            "你是一位知识图谱专家。根据提供的课程知识库，"
            "生成一份 Mermaid mindmap 格式的思维导图。"
            "根节点为课程主题，然后按概念层次逐级展开子节点。"
            "难度与学生的 knowledge_level 匹配，"
            "使用中文标签。"
        )
        user_content = (
            f"主题：{topic}\n难度：{difficulty}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请只输出 Mermaid mindmap 代码块。"

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

        lower = topic.lower()
        mindmap = (
            "mindmap\n"
            f"  root(({topic} - {label}))\n"
            f"    概念定义\n"
            f"      直观理解\n"
            f"      形式化定义\n"
            f"    核心原理\n"
            f"      数学基础\n"
            f"      算法流程\n"
            f"    应用场景\n"
            f"      经典案例\n"
            f"      实际项目\n"
            f"    常见误区\n"
            f"      易混淆概念\n"
            f"      典型错误\n"
            f"    关联知识\n"
            f"      前置概念\n"
            f"      后续进阶\n"
        )

        content = f"```mermaid\n{mindmap}\n```\n"
        if rag_context:
            content += f"\n<!-- 知识库参考片段已用于生成 -->\n"

        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} 思维导图",
                content=content,
                content_format="mermaid",
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
            resource_type=ResourceType.MIND_MAP,
            title=draft.title or f"{topic} 思维导图",
            content=draft.content,
            content_format="mermaid",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
