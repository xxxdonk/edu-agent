from __future__ import annotations

import re

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import subject_context_from_profile

from .base import BaseResourceAgent
from .drafts import ReadingDraft
from .cross_subject import reading_resource, should_use_cross_subject


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
        subject = subject_context_from_profile(context.profile)
        system_prompt = (
            f"你是一位{subject.subject_name or '通识'}课程研究助理。根据当前学科和可用资料生成分层拓展阅读。"
            "私有输出固定为 objective、quick_read、deep_read、project_route、glossary、"
            "check_questions、recommended_practice。project_route 为 3 至 6 步阅读路线，"
            "glossary 为 8 至 12 个“术语：解释”，check_questions 为 5 至 8 个检查问题。"
            "quick_read 提炼十分钟可掌握的背景与结论，deep_read 展开原理、方法和应用。"
            "不要输出 Markdown 标题、资源元数据、来源字段或外部 URL，"
            f"阅读结构必须适合 {subject.subject_family} 学科，不得复制讲解正文。"
            "也不要虚构论文、统计数据、链接或无法核验的事实。"
            "避免复述课程讲解，重点放在延伸联系、阅读顺序和带问题阅读。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"学习历史：{context.profile.learning_history.value}\n"
            f"学习目标：{context.profile.learning_goals.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请严格按私有 JSON schema 返回分层阅读结构。"
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
        if should_use_cross_subject(context):
            return reading_resource(context, topic, difficulty, references)
        draft = ReadingDraft(
            objective=(
                f"沿课程来源建立{topic}的延伸阅读路线，并把概念、实验判断与项目决策连接起来。"
            ),
            quick_read=(
                f"先用十分钟确认{topic}解决什么问题、需要哪些输入、输出如何评价。"
                "阅读时优先寻找任务假设、数据条件和验证方法，不急于记忆实现细节。"
                "完成后应能说清基线、训练结果和验证结果分别回答什么问题。"
            ),
            deep_read=(
                f"深入阅读时，沿“问题定义—数据准备—目标函数—参数学习—泛化验证”追踪{topic}。"
                "对每个环节记录一个可观察证据：数据分布是否合理、损失是否稳定下降、"
                "训练与验证差距是否扩大、指标是否匹配学习目标。再比较不同设置，"
                "区分由数据、模型复杂度和优化参数造成的现象。"
            ),
            project_route=[
                "先阅读来源中的任务定义与评价指标，写出项目成功标准。",
                "再阅读数据划分和预处理部分，列出可能的信息泄漏点。",
                "随后阅读训练与验证流程，建立一份可复现实验记录。",
                "最后阅读常见错误与调参建议，只选择有证据的问题进行调整。",
            ],
            glossary=[
                "特征：模型用于预测的输入变量",
                "标签：监督学习中希望预测的目标",
                "基线：用于比较后续方案的简单参考结果",
                "损失函数：衡量预测与目标偏差的训练目标",
                "学习率：控制单次参数更新幅度的超参数",
                "训练集：用于拟合模型参数的数据",
                "验证集：用于模型选择和泛化检查的数据",
                "过拟合：训练表现好但新数据表现明显下降",
                "正则化：限制模型复杂度以改善泛化的方法",
                "数据泄漏：训练过程使用了本不应获得的信息",
            ],
            check_questions=[
                f"{topic}的输入、输出和评价指标分别是什么？",
                "为什么需要先建立基线？",
                "哪些预处理步骤必须只在训练集上拟合？",
                "训练和验证曲线分离通常提示什么问题？",
                "一次参数调整应保留哪些实验记录？",
                "如何判断结果能支持项目目标而不是偶然波动？",
            ],
            recommended_practice=(
                f"选择一个小型分类任务，按阅读路线建立{topic}实验清单。"
                "固定数据划分和评价指标，仅改变一个设置，并用表格记录调整前后的验证结果与解释。"
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
        objective = self._normalize_paragraph(draft.objective)
        quick_read = self._normalize_paragraph(draft.quick_read)
        deep_read = self._normalize_paragraph(draft.deep_read)
        project_route = [self._normalize_list_item(point) for point in draft.project_route]
        glossary = [self._normalize_list_item(point) for point in draft.glossary]
        questions = [self._normalize_list_item(point) for point in draft.check_questions]
        practice = self._normalize_paragraph(draft.recommended_practice)
        source_lines = [
            f"- {reference.title}（{reference.locator}）"
            for reference in references
        ] or ["- 本轮没有可展示的可靠来源"]
        content = "\n".join(
            [
                f"# {topic} 拓展阅读",
                "",
                "## 1. 阅读目标",
                objective,
                "",
                "## 2. 10 分钟快速阅读",
                quick_read,
                "",
                "## 3. 20 至 40 分钟深入阅读",
                deep_read,
                "",
                "## 4. 项目阅读路线",
                *[f"{index}. {point}" for index, point in enumerate(project_route, start=1)],
                "",
                "## 5. 关键术语表",
                *[f"- {point}" for point in glossary],
                "",
                "## 6. 阅读检查问题",
                *[f"{index}. {point}" for index, point in enumerate(questions, start=1)],
                "",
                "## 7. 推荐实践",
                practice,
                "",
                "## 8. 真实 RAG 来源",
                *source_lines,
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
