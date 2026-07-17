from __future__ import annotations

import json

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent


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
            "你是一位机器学习课程助教。根据课程知识库，生成一份分层练习题。"
            "必须包含三个难度层次：基础题（单选）、进阶题（简答）和挑战题（综合）。"
            "每道题包含题目、选项（选择题）、答案和解析。"
            "难度与学生的 knowledge_level 匹配，从基础开始逐步提升。"
            "输出 JSON 格式。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"薄弱点：{context.profile.weak_topics.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请输出包含 questions 数组的 JSON。"

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

        questions = {
            "topic": topic,
            "difficulty": difficulty,
            "questions": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "level": "basic",
                    "question": f"以下关于{topic}的描述，哪一项是正确的？",
                    "options": [
                        "A. 选项一（正确描述）",
                        "B. 选项二（常见误区）",
                        "C. 选项三（易混淆概念）",
                        "D. 选项四（无关描述）",
                    ],
                    "answer": "A",
                    "explanation": f"这是{topic}的正确定义，注意区分常见误区。",
                },
                {
                    "id": "q2",
                    "type": "single_choice",
                    "level": "basic",
                    "question": f"{topic}的核心目标是什么？",
                    "options": [
                        "A. 最大化训练误差",
                        "B. 最小化目标函数",
                        "C. 增加模型复杂度",
                        "D. 减少数据量",
                    ],
                    "answer": "B",
                    "explanation": f"{topic}的优化目标是找到使目标函数最小的参数。",
                },
                {
                    "id": "q3",
                    "type": "short_answer",
                    "level": "intermediate",
                    "question": f"请简述{topic}的算法流程，不超过200字。",
                    "answer": f"1. 初始化参数；2. 计算当前梯度；3. 沿负梯度方向更新参数；4. 重复至收敛。",
                    "explanation": "重点考察对算法步骤的完整理解。",
                },
                {
                    "id": "q4",
                    "type": "comprehensive",
                    "level": "advanced",
                    "question": f"在实际项目中应用{topic}时，可能遇到哪些问题？如何解决？",
                    "answer": "主要问题包括：1. 局部最优；2. 收敛速度慢；3. 超参数敏感。解决方法：使用动量、自适应学习率、正则化等技术。",
                    "explanation": "综合考察实践应用能力。",
                },
            ],
        }

        content = json.dumps(questions, ensure_ascii=False, indent=2)
        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} 分层练习题",
                content=content,
                content_format="json",
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
            resource_type=ResourceType.QUIZ,
            title=draft.title or f"{topic} 分层练习题",
            content=draft.content,
            content_format="json",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
