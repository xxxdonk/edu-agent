from __future__ import annotations

import asyncio

import pytest

from app.orchestrator import SharedAgentContext
from app.planner import DevelopmentPlannerAgent
from app.profile import DevelopmentProfileAgent
from app.resources.coding_agent import CodingAgent
from app.resources.explanation_agent import ExplanationAgent
from app.resources.mindmap_agent import MindMapAgent
from app.resources.quiz_agent import QuizAgent
from app.resources.reading_agent import ReadingAgent
from app.resources.reviewer import ReviewerAgent
from app.schemas import ProfileChatRequest, ResourceGenerationRequest
from app.schemas.profile import ChatMessage
from app.subjects import infer_subject_context


MACHINE_LEARNING_LEAKAGE = ("机器学习", "逻辑回归", "客户流失", "模型训练", "sklearn")


@pytest.mark.parametrize(
    ("text", "current_course", "subject", "family", "stage"),
    [
        ("怎么学高中数学", None, "高中数学", "mathematics", "high_school"),
        ("我上高中", "高中数学", "高中数学", "mathematics", "high_school"),
        ("我是高二学生，函数很差", "高中数学", "高中数学", "mathematics", "high_school"),
        ("我想提高高中语文阅读理解", None, "高中语文", "language", "high_school"),
        ("我准备高中英语期末考试", None, "高中英语", "language", "high_school"),
        ("我不会高中物理力学", None, "高中物理", "natural_science", "high_school"),
        ("我想复习高中化学有机化学", None, "高中化学", "natural_science", "high_school"),
        ("初中历史怎么背", None, "初中历史", "social_science", "middle_school"),
        ("地理综合题总是不会", None, "地理", "social_science", "unknown"),
        ("我要学高等数学极限", None, "高等数学", "mathematics", "unknown"),
        ("线性代数矩阵不会", None, "线性代数", "mathematics", "unknown"),
        ("大学英语四级怎么复习", None, "大学英语", "language", "undergraduate"),
        ("Java 零基础", None, "Java", "computer_science", "unknown"),
        ("数据结构二叉树", None, "数据结构", "computer_science", "unknown"),
        ("计算机组成原理存储系统", None, "计算机组成原理", "computer_science", "unknown"),
        ("自动控制原理根轨迹", None, "自动控制原理", "engineering", "unknown"),
        ("嵌入式 STM32 中断", None, "嵌入式系统", "engineering", "unknown"),
        ("机器学习逻辑回归", None, "机器学习", "computer_science", "unknown"),
        ("我想学经济学", None, "经济学", "business_economics", "unknown"),
        ("我想学画画", None, "绘画", "arts", "unknown"),
    ],
)
def test_subject_matrix(text, current_course, subject, family, stage):
    context = infer_subject_context(text, current_course=current_course)
    assert context.subject_name == subject
    assert context.subject_family == family
    assert context.education_stage == stage
    if subject != "机器学习":
        assert not any(term in context.subject_name for term in MACHINE_LEARNING_LEAKAGE)


def request(student_id: str, *messages: str) -> ProfileChatRequest:
    return ProfileChatRequest(
        student_id=student_id,
        conversation_id=f"conversation-{student_id}",
        messages=[
            ChatMessage(message_id=f"message-{index}", role="user", content=message)
            for index, message in enumerate(messages, 1)
        ],
    )


def test_high_school_profile_asks_grade_not_major_and_does_not_repeat_answered_course():
    agent = DevelopmentProfileAgent()
    first = agent.extract(request("math-student", "怎么学高中数学"), None)
    assert first.profile.course.value == "高中数学"
    assert first.profile.major.value == "高中"
    assert first.next_question == "你目前是高一、高二还是高三？"
    assert "专业" not in first.next_question

    second = agent.extract(
        request("math-student", "怎么学高中数学", "我上高中", "我是高二学生，函数很差"),
        first.profile,
    )
    assert second.profile.major.value == "高二"
    assert second.profile.course.value == "高中数学"
    assert second.next_question != first.next_question
    assert "专业" not in (second.next_question or "")


def test_course_switch_clears_old_subject_specific_fields():
    agent = DevelopmentProfileAgent()
    machine_learning = agent.extract(
        request("switch-student", "我在学机器学习，逻辑回归很薄弱，希望完成分类项目"),
        None,
    ).profile
    switched = agent.extract(
        request("switch-student", "我想从机器学习改学高中英语，阅读理解较弱"),
        machine_learning,
    ).profile
    assert switched.course.value == "高中英语"
    joined = " ".join([*switched.weak_topics.value, *switched.learning_goals.value])
    assert "逻辑回归" not in joined
    assert "分类项目" not in joined


def test_planner_and_five_resources_follow_high_school_math_without_leakage():
    profile = DevelopmentProfileAgent().extract(
        request(
            "resource-math-student",
            "我是高二学生，正在学习高中数学，函数和数列较弱，目标是期末考试，每天学习45分钟，喜欢图示和例题",
        ),
        None,
    ).profile
    path = DevelopmentPlannerAgent().generate(profile)
    path_text = " ".join([path.course, *(step.topic for step in path.steps), *(step.learning_goal for step in path.steps)])
    assert 3 <= len(path.steps) <= 8
    assert "高中数学" in path_text
    assert "高中数学：错题复盘与模拟练习" in [step.topic for step in path.steps]
    assert not any("每天学习" in step.topic or "喜欢图示" in step.topic for step in path.steps)
    assert not any(term in path_text for term in MACHINE_LEARNING_LEAKAGE)

    context = SharedAgentContext(
        task_id="cross-subject-task",
        request=ResourceGenerationRequest(student_id=profile.student_id, path_id=path.path_id, step=1),
        profile=profile,
        path=path,
    )
    agents = [ExplanationAgent(), MindMapAgent(), QuizAgent(), ReadingAgent(), CodingAgent()]
    resources = [asyncio.run(agent.generate(context)) for agent in agents]
    for resource in resources:
        searchable = f"{resource.title} {resource.target_topic} {resource.content}"
        assert not any(term in searchable for term in MACHINE_LEARNING_LEAKAGE)
        assert any(ref.source_id == "general-model" for ref in resource.source_references)
        reviewed = asyncio.run(ReviewerAgent().review(resource, context))
        assert reviewed.review_status == "approved"
    coding = next(resource for resource in resources if resource.resource_type.value == "coding")
    assert "计算与实验实践" in coding.title


def test_non_computational_coding_type_becomes_application_task():
    profile = DevelopmentProfileAgent().extract(
        request("history-student", "我是高二学生，想学习高中历史，材料题较弱，目标是期末考试"),
        None,
    ).profile
    path = DevelopmentPlannerAgent().generate(profile)
    context = SharedAgentContext(
        task_id="history-task",
        request=ResourceGenerationRequest(student_id=profile.student_id, path_id=path.path_id, step=1),
        profile=profile,
        path=path,
    )
    resource = asyncio.run(CodingAgent().generate(context))
    assert resource.resource_type.value == "coding"
    assert resource.content_format == "markdown"
    assert "应用实践任务" in resource.title
    assert "```python" not in resource.content
    assert asyncio.run(ReviewerAgent().review(resource, context)).review_status == "approved"


def test_key_demo_subjects_have_subject_specific_formula_quiz_and_practice():
    agent = DevelopmentProfileAgent()
    cases = (
        ("math-depth", "我是高二学生，想提高高中数学，函数和数列较弱，目标是期末考试", "f(3)", "等差数列"),
        ("english-depth", "我是大学生，准备大学英语考试，阅读和写作较弱", "grammatically complete", "应用实践任务"),
        ("control-depth", "我是自动化专业学生，正在复习自动控制原理，根轨迹和频率响应较弱", "左半平面", "G(jw)"),
    )
    for student_id, text, quiz_token, practice_token in cases:
        profile = agent.extract(request(student_id, text), None).profile
        path = DevelopmentPlannerAgent().generate(profile)
        context = SharedAgentContext(
            task_id=f"{student_id}-task",
            request=ResourceGenerationRequest(student_id=student_id, path_id=path.path_id, step=1),
            profile=profile,
            path=path,
        )
        quiz = asyncio.run(QuizAgent().generate(context))
        practice = asyncio.run(CodingAgent().generate(context))
        assert quiz_token in quiz.content
        assert practice_token in practice.content
        if student_id == "control-depth":
            explanation = asyncio.run(ExplanationAgent().generate(context))
            assert r"\(T(s)=\frac{G(s)}{1+G(s)H(s)}\)" in explanation.content
