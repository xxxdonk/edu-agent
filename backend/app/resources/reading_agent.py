from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent


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
            "你是一位机器学习领域的研究助理。根据课程知识库，"
            "生成一份拓展阅读材料，包含：文献推荐、经典论文导读、"
            "相关资源链接和进阶学习路径。"
            "用 Markdown 格式组织，难度与学生水平匹配。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"学习历史：{context.profile.learning_history.value}\n"
            f"学习目标：{context.profile.learning_goals.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请生成 Markdown 格式的拓展阅读文档。"

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

        content = (
            f"# {topic} — 拓展阅读（{label}）\n\n"
            f"## 推荐文献\n"
            f"- **经典论文**：待补充（建议查阅 Google Scholar 上 {topic} 相关的高引论文）\n"
            f"- **综述文章**：可在 arXiv 上搜索 `{topic}` 的最新综述\n"
            f"- **教材章节**：参考《机器学习》（周志华）或《统计学习方法》（李航）中相关章节\n\n"
            f"## 经典论文导读\n"
            f"（本节建议结合课程知识库中的原始文献阅读）\n\n"
            f"## 相关资源\n"
            f"- 在线课程：Coursera / 吴恩达机器学习课程中关于 {topic} 的视频\n"
            f"- 代码实现：GitHub 上搜索 `{topic}` 的 Python 实现\n"
            f"- 博客文章：Towards Data Science / Medium 上的相关教程\n\n"
            f"## 进阶路径\n"
            f"1. 掌握 {topic} 的基本概念和数学原理\n"
            f"2. 阅读 1-2 篇经典论文，理解问题背景\n"
            f"3. 复现代码实现，加深理解\n"
            f"4. 阅读最新研究进展，了解前沿方向\n\n"
            f"## 学习建议\n"
            f"- 建议先完成课程讲解文档，再阅读拓展材料\n"
            f"- 阅读论文时重点关注方法动机和实验设计\n"
            f"- 遇到不懂的数学推导可先跳过，把握整体思路\n"
        )
        if rag_context:
            content += f"\n---\n## 知识库参考\n{rag_context}\n"

        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} 拓展阅读材料",
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
            resource_type=ResourceType.READING,
            title=draft.title or f"{topic} 拓展阅读材料",
            content=draft.content,
            content_format="markdown",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
