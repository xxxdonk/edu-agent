from __future__ import annotations

import json

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent
from .drafts import QuizDraft


class QuizAgent(BaseResourceAgent):
    agent_name = "quiz_agent"
    resource_type = ResourceType.QUIZ

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
            "你是一位机器学习课程助教。只依据提供的课程知识库生成恰好三道题。"
            "私有输出固定为 basic、intermediate、challenge 三个字段："
            "basic 是一道基础单选题，必须有且仅有四个选项、唯一答案和解析；"
            "intermediate 是一道进阶简答题，必须有答案和解析；"
            "challenge 是一道挑战综合题，必须有答案和解析。"
            "不要生成题目 ID、资源元数据、来源字段或 Markdown。"
            "事实、术语和答案必须能够由课程知识库支持。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"薄弱点：{context.profile.weak_topics.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += (
            "请严格按私有 JSON schema 输出：基础单选、进阶简答、挑战综合各一题。"
        )
        messages = [LLMMessage(role="user", content=user_content)]

        return await self._generate_with_one_format_repair(
            system_prompt=system_prompt,
            messages=messages,
            response_model=QuizDraft,
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
        draft = QuizDraft.model_validate(
            {
                "basic": {
                    "question": f"以下关于{topic}的描述，哪一项是正确的？",
                    "options": [
                        "A. 应先明确目标函数，再依据数据和优化规则更新模型参数",
                        "B. 训练时应始终让目标函数持续增大",
                        "C. 算法效果只由样本数量决定，与参数设置无关",
                        "D. 不需要验证集也能可靠判断模型泛化能力",
                    ],
                    "answer": "A",
                    "explanation": (
                        f"学习{topic}时需要把概念、目标函数、参数更新和验证过程联系起来。"
                    ),
                },
                "intermediate": {
                    "question": f"请简述{topic}的主要流程及每一步的目的。",
                    "answer": (
                        "先明确问题与目标函数，再准备数据并初始化模型参数；"
                        "随后依据目标函数计算更新方向，迭代训练，并用独立数据验证效果。"
                    ),
                    "explanation": "重点考察对目标、训练过程和验证环节之间关系的完整理解。",
                },
                "challenge": {
                    "question": f"在分类项目中应用{topic}时，如何发现并处理训练效果不佳的问题？",
                    "answer": (
                        "先比较训练集与验证集表现，检查数据质量、目标函数和参数设置；"
                        "再针对收敛、过拟合或欠拟合问题调整学习率、正则化和模型复杂度。"
                    ),
                    "explanation": "综合考察诊断问题、选择调整方法和验证改进效果的能力。",
                },
            }
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
        draft: QuizDraft,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        resource_id = self._make_resource_id()
        questions = [
            {
                "id": f"{resource_id}::q1",
                "type": "single_choice",
                "level": "basic",
                "question": draft.basic.question,
                "options": draft.basic.options,
                "answer": draft.basic.answer,
                "explanation": draft.basic.explanation,
            },
            {
                "id": f"{resource_id}::q2",
                "type": "short_answer",
                "level": "intermediate",
                "question": draft.intermediate.question,
                "answer": draft.intermediate.answer,
                "explanation": draft.intermediate.explanation,
            },
            {
                "id": f"{resource_id}::q3",
                "type": "comprehensive",
                "level": "advanced",
                "question": draft.challenge.question,
                "answer": draft.challenge.answer,
                "explanation": draft.challenge.explanation,
            },
        ]
        content = json.dumps(
            {
                "topic": topic,
                "difficulty": difficulty,
                "questions": questions,
            },
            ensure_ascii=False,
            indent=2,
        )
        return Resource(
            resource_id=resource_id,
            resource_type=ResourceType.QUIZ,
            title=f"{topic} 分层练习题",
            content=content,
            content_format="json",
            target_topic=topic,
            difficulty=Difficulty(difficulty),
            personalization_reason=self._personalization_reason(context),
            source_references=references,
            review_status="pending",
        )
