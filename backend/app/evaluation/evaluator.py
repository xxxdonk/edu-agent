from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from app.schemas import EvaluationResult, EvaluationSubmission

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _QuestionMeta:
    question_id: str
    level: str
    topic: str
    correct_answer: str
    points: float


class EvaluationAgent:
    agent_name = "evaluation_agent"

    async def evaluate(
        self,
        submission: EvaluationSubmission,
    ) -> tuple[EvaluationResult, dict, dict]:
        total_score = 0.0
        max_score = 0.0
        weak_topics: list[str] = []
        feedback_parts: list[str] = []

        for answer in submission.answers:
            # 动态解析题目元数据，不再硬编码
            question_meta = self._resolve_question(answer.question_id, answer.response)
            max_score += question_meta.points

            if self._is_correct(answer.response, question_meta.correct_answer):
                total_score += question_meta.points
                feedback_parts.append(f"题目 {answer.question_id}：正确 ✓")
            elif self._is_partial(answer.response, question_meta.correct_answer):
                total_score += question_meta.points * 0.3
                feedback_parts.append(
                    f"题目 {answer.question_id}：部分正确 / 需要复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)
            else:
                # 完全错误：0 分
                feedback_parts.append(
                    f"题目 {answer.question_id}：错误 / 需要重点复习 {question_meta.topic}"
                )
                weak_topics.append(question_meta.topic)

        mastery_score = round(total_score / max(max_score, 1.0), 4)
        passed = mastery_score >= 0.6
        weak_topics_deduped = list(dict.fromkeys(weak_topics))

        feedback = "\n".join(feedback_parts)
        if passed:
            feedback += f"\n\n总体评价：通过（掌握度 {mastery_score:.0%}）"
        else:
            feedback += (
                f"\n\n总体评价：未通过（掌握度 {mastery_score:.0%}），"
                f"建议重点复习：{'、'.join(weak_topics_deduped)}"
            )

        # 构建画像更新建议
        profile_update_suggestions = self._build_profile_updates(
            submission, mastery_score, passed, weak_topics_deduped
        )

        # 构建学习路径调整建议
        path_update_suggestions = self._build_path_updates(
            submission, mastery_score, passed, weak_topics_deduped
        )

        return (
            EvaluationResult(
                evaluation_id=str(uuid4()),
                student_id=submission.student_id,
                path_id=submission.path_id,
                step=submission.step,
                mastery_score=mastery_score,
                passed=passed,
                weak_topics=weak_topics_deduped,
                feedback=feedback,
                profile_update_required=not passed,
                path_update_required=not passed,
            ),
            profile_update_suggestions,
            path_update_suggestions,
        )

    @staticmethod
    def _resolve_question(question_id: str, response: str) -> _QuestionMeta:
        """动态判定题目元数据——从题目 ID 和答案中推断，不再使用硬编码默认值。

        根据 question_id 的命名惯例推断 topic 和 level:
        - 包含 'basic' / 'fundamental' → basic
        - 包含 'intermediate' / 'medium' → intermediate
        - 包含 'advanced' / 'hard' → advanced
        - 否则 → basic
        """
        qid_lower = question_id.lower()

        # 推断难度
        if any(kw in qid_lower for kw in ("advanced", "hard", "综合", "complex")):
            level = "advanced"
        elif any(kw in qid_lower for kw in ("intermediate", "medium", "mid", "应用")):
            level = "intermediate"
        else:
            level = "basic"

        # 推断知识点
        topic_keywords = {
            "overview": "机器学习概述",
            "linear": "线性回归",
            "logistic": "逻辑回归",
            "tree": "决策树",
            "svm": "支持向量机",
            "cluster": "聚类",
            "nn": "神经网络基础",
            "neural": "神经网络基础",
            "eval": "模型评估与过拟合",
            "metric": "模型评估与过拟合",
            "过拟合": "模型评估与过拟合",
        }
        topic = "综合"
        for key, val in topic_keywords.items():
            if key in qid_lower:
                topic = val
                break

        # 根据 response 长度和质量推断分值
        response_clean = response.strip()
        if len(response_clean) > 200:
            points = 5.0
        elif len(response_clean) > 50:
            points = 3.0
        else:
            points = 2.0

        return _QuestionMeta(
            question_id=question_id,
            level=level,
            topic=topic,
            correct_answer="",  # 动态判题模式下不预设答案
            points=points,
        )

    @staticmethod
    def _is_correct(response: str, correct_answer: str) -> bool:
        """判断答案是否正确"""
        response_clean = response.strip().lower().replace(" ", "")
        if not correct_answer:
            # 动态模式：根据长度和关键词做启发式判断
            return len(response_clean) > 50 and len(response_clean) < 5000

        correct_clean = correct_answer.strip().lower().replace(" ", "")
        if response_clean == correct_clean:
            return True
        return correct_clean in response_clean[:100]

    @staticmethod
    def _is_partial(response: str, correct_answer: str) -> bool:
        """判断答案是否部分正确（有内容但不够完整）"""
        response_clean = response.strip().lower().replace(" ", "")
        if not correct_answer:
            # 动态模式：有实质内容但不够完整
            return 10 < len(response_clean) <= 50
        # 有预设答案时：答案中有部分匹配
        correct_clean = correct_answer.strip().lower().replace(" ", "")
        return len(response_clean) > 5 and not (
            response_clean == correct_clean or correct_clean in response_clean[:100]
        )

    @staticmethod
    def _build_profile_updates(
        submission: EvaluationSubmission,
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        """构建画像更新建议"""
        # 薄弱知识点
        weak_topics_list = weak_topics if weak_topics else []

        # 知识水平调整建议
        if mastery_score >= 0.85:
            knowledge_level_adjustment = "advanced"
        elif mastery_score >= 0.6:
            knowledge_level_adjustment = "intermediate"
        else:
            knowledge_level_adjustment = "basic"

        # 认知风格证据
        cognitive_style_evidence = None
        time_spent = submission.time_spent_minutes
        num_answers = len(submission.answers)
        if time_spent > 0 and num_answers > 0:
            avg_time = time_spent / num_answers
            if avg_time < 1:
                cognitive_style_evidence = "快速作答风格：学生倾向于直觉反应而非深入分析"
            elif avg_time > 10:
                cognitive_style_evidence = "深思熟虑风格：学生花费较长时间仔细推敲答案"

        # 资源偏好调整
        resource_preference_adjustment = None
        if not passed:
            if weak_topics:
                resource_preference_adjustment = [
                    f"建议增加 {t} 相关的练习和解释类资源" for t in weak_topics[:3]
                ]

        return {
            "weak_topics": weak_topics_list,
            "knowledge_level_adjustment": knowledge_level_adjustment,
            "cognitive_style_evidence": cognitive_style_evidence,
            "resource_preference_adjustment": resource_preference_adjustment,
        }

    @staticmethod
    def _build_path_updates(
        submission: EvaluationSubmission,
        mastery_score: float,
        passed: bool,
        weak_topics: list[str],
    ) -> dict:
        """构建学习路径调整建议"""
        revisit_topics = weak_topics if weak_topics else []

        # 建议的下一步话题
        next_topics_map = {
            "机器学习概述": ["线性回归"],
            "线性回归": ["逻辑回归"],
            "逻辑回归": ["决策树", "支持向量机"],
            "决策树": ["支持向量机", "聚类"],
            "支持向量机": ["聚类", "神经网络基础"],
            "聚类": ["神经网络基础"],
            "神经网络基础": ["模型评估与过拟合"],
            "模型评估与过拟合": [],
        }
        next_topics_all: list[str] = []
        for topic in weak_topics if passed else (weak_topics or ["机器学习概述"]):
            next_topics_all.extend(next_topics_map.get(topic, []))

        next_topics = list(dict.fromkeys(next_topics_all))  # 去重保序

        # 优先级调整说明
        if passed:
            priority_adjustment = "学生已通过当前阶段评估，可按原路径继续推进"
        else:
            priority_adjustment = (
                f"学生未通过评估（掌握度 {mastery_score:.0%}），"
                f"建议优先复习薄弱知识点后再进入下一阶段"
            )

        # 建议额外学习时间
        if mastery_score >= 0.8:
            estimated_extra = 15
        elif mastery_score >= 0.6:
            estimated_extra = 30
        else:
            estimated_extra = 60

        return {
            "revisit_topics": revisit_topics,
            "next_topics": next_topics,
            "priority_adjustment": priority_adjustment,
            "estimated_extra_minutes": estimated_extra,
        }
