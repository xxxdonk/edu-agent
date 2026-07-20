from __future__ import annotations

import json

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import subject_context_from_profile

from .base import BaseResourceAgent
from .drafts import ExpandedQuizDraft
from .cross_subject import quiz_resource, should_use_cross_subject


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
        subject = subject_context_from_profile(context.profile)
        system_prompt = (
            f"你是一位{subject.subject_name or '通识'}课程助教。根据当前学科和可用资料生成 8 至 12 道分层题。"
            "私有输出固定为 basic、intermediate、challenge 三个数组："
            "basic 包含 3 至 4 道基础单选题，每题必须有四个不重复选项、唯一答案和解析；"
            "intermediate 包含 3 至 5 道原理或应用简答题；"
            "challenge 包含 2 至 3 道项目场景综合题。"
            "题目应覆盖定义、辨析、公式、流程、错误诊断、应用和结果解释，"
            "至少两题直接联系学生目标，题干之间不得只是改写。"
            "不要生成题目 ID、资源元数据、来源字段或 Markdown。"
            f"题目必须符合 {subject.subject_family} 学科特点，事实、术语和答案必须与当前课程一致。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"薄弱点：{context.profile.weak_topics.value}\n"
            f"学习目标：{context.profile.learning_goals.value}\n"
            f"资源偏好：{context.profile.resource_preference.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += (
            "请严格按私有 JSON schema 输出分层题目数组，答案必须能由解析支持。"
        )
        messages = [LLMMessage(role="user", content=user_content)]

        return await self._generate_with_one_format_repair(
            system_prompt=system_prompt,
            messages=messages,
            response_model=ExpandedQuizDraft,
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
            return quiz_resource(context, topic, difficulty, references)
        goal = "、".join(context.profile.learning_goals.value or ["完成当前学习任务"])
        weak = "、".join(context.profile.weak_topics.value or [topic])
        draft = ExpandedQuizDraft.model_validate(
            {
                "basic": [
                    {
                        "question": f"以下关于{topic}学习流程的描述，哪一项正确？",
                        "options": [
                            "A. 先明确任务和评价指标，再选择模型与训练方法",
                            "B. 只要训练轮数足够，验证集就不再需要",
                            "C. 模型效果只由样本数量决定",
                            "D. 所有参数都应设为相同数值",
                        ],
                        "answer": "A",
                        "explanation": "可靠流程从任务、数据和指标出发，并通过独立数据验证泛化表现。",
                    },
                    {
                        "question": f"学习{topic}时，验证集最主要的作用是什么？",
                        "options": [
                            "A. 代替训练集更新全部参数",
                            "B. 评估未参与训练的数据表现并辅助模型选择",
                            "C. 保证模型一定达到百分之百准确率",
                            "D. 删除所有预测错误的样本",
                        ],
                        "answer": "B",
                        "explanation": "验证集用于比较方案和识别过拟合，不直接承担常规参数训练。",
                    },
                    {
                        "question": f"关于{topic}中的损失函数，哪一项理解更准确？",
                        "options": [
                            "A. 它只负责保存原始数据",
                            "B. 它衡量预测与目标的偏差并指导优化",
                            "C. 它与模型参数完全无关",
                            "D. 它越大通常代表拟合越好",
                        ],
                        "answer": "B",
                        "explanation": "损失函数把预测误差转化为可优化目标，训练通常尝试降低该目标。",
                    },
                ],
                "intermediate": [
                    {
                        "question": f"请按顺序说明{topic}的训练与验证流程。",
                        "answer": "明确任务与指标，准备并划分数据，训练模型，再在验证集比较结果并记录误差。",
                        "explanation": "考察是否能把目标、数据、训练和验证组织成完整流程。",
                    },
                    {
                        "question": f"如果训练误差持续下降而验证误差上升，应如何解释和处理？",
                        "answer": "这通常提示过拟合，可检查数据划分，并尝试正则化、降低复杂度或早停。",
                        "explanation": "训练与验证走势分离是判断泛化问题的重要证据，处理后仍需重新验证。",
                    },
                    {
                        "question": f"围绕薄弱点“{weak}”，列出两项可验证的排查动作。",
                        "answer": "先核对输入、标签和预处理，再固定评价指标比较基线与调整后结果。",
                        "explanation": "排查应落到可观察的数据与指标，不能只凭主观判断。",
                    },
                ],
                "challenge": [
                    {
                        "question": f"为目标“{goal}”设计一个使用{topic}的最小实验，并说明成功标准。",
                        "answer": "选定小规模可复现数据，建立基线，固定划分和指标，完成训练与验证；成功标准是过程可复现且验证指标优于基线。",
                        "explanation": "项目题同时考察任务拆解、实验控制和结果解释。",
                    },
                    {
                        "question": f"在分类项目中应用{topic}后结果不稳定，你会如何定位原因并决定下一步？",
                        "answer": "固定随机种子与数据划分，检查类别分布和预处理，重复实验比较波动，再根据证据调整模型复杂度、正则化或参数范围。",
                        "explanation": "先控制变量和确认问题来源，再进行有依据的调整，避免盲目调参。",
                    },
                    {
                        "question": f"比较两个{topic}方案时，为什么不能只看训练准确率？请给出项目决策依据。",
                        "answer": "训练准确率不能代表泛化能力；应在相同数据划分下比较验证指标、稳定性、复杂度和业务目标，再选择方案。",
                        "explanation": "综合评价需要同时考虑泛化、可复现性和项目约束。",
                    },
                ],
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
        draft: ExpandedQuizDraft,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        resource_id = self._make_resource_id()
        questions: list[dict] = []
        for question in draft.basic:
            questions.append({
                "type": "single_choice", "level": "basic",
                **question.model_dump(),
            })
        for question in draft.intermediate:
            questions.append({
                "type": "short_answer", "level": "intermediate",
                **question.model_dump(),
            })
        for question in draft.challenge:
            questions.append({
                "type": "comprehensive", "level": "advanced",
                **question.model_dump(),
            })
        for index, question in enumerate(questions, start=1):
            question["id"] = f"{resource_id}::q{index}"
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
