from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from app.orchestrator import SharedAgentContext
from app.planner import DevelopmentPlannerAgent
from app.profile import DevelopmentProfileAgent
from app.resources.reviewer import ReviewerAgent
from app.schemas import (
    ProfileChatRequest,
    Resource,
    ResourceGenerationRequest,
    ResourceType,
    SourceReference,
)
from app.schemas.profile import ChatMessage


def _context() -> SharedAgentContext:
    request = ProfileChatRequest(
        student_id="review-test-student",
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "我是人工智能专业学生，刚开始学习机器学习，数学基础比较一般。"
                    "我希望完成分类项目，喜欢图示和代码案例，每天学习30分钟。"
                ),
            )
        ],
    )
    profile = DevelopmentProfileAgent().extract(request, None).profile
    path = DevelopmentPlannerAgent().generate(profile)
    generation_request = ResourceGenerationRequest(
        student_id=profile.student_id,
        path_id=path.path_id,
        step=1,
        resource_types=[ResourceType.EXPLANATION],
    )
    return SharedAgentContext(
        task_id="review-test-task",
        request=generation_request,
        profile=profile,
        path=path,
    )


def _resource(
    context: SharedAgentContext,
    *,
    resource_type: ResourceType = ResourceType.EXPLANATION,
    content: str | None = None,
    content_format: str = "markdown",
) -> Resource:
    weak_topic = context.profile.weak_topics.value[0]
    return Resource(
        resource_id=str(uuid4()),
        resource_type=resource_type,
        title="机器学习个性化学习材料",
        content=content
        or (
            "# 线性模型基础\n\n本材料解释输入特征、模型参数和预测结果之间的关系，"
            "并通过一个分类示例帮助学习者理解训练、验证和测试的区别。"
        ),
        content_format=content_format,
        target_topic=context.path.steps[0].topic,
        difficulty=context.profile.knowledge_level.value,
        personalization_reason=(
            f"针对学生的{weak_topic}薄弱点，并结合图示偏好与分类项目目标进行讲解。"
        ),
        source_references=[
            SourceReference(
                source_id="ml-chapter-02",
                title="线性回归",
                locator="data/machine_learning/02-线性回归.md#知识正文",
                chunk_id="chapter-02-chunk-003",
            )
        ],
        review_status="pending",
    )


def test_reviewer_returns_public_resource_and_approves_clean_content() -> None:
    context = _context()

    reviewed = asyncio.run(ReviewerAgent().review(_resource(context), context))

    assert isinstance(reviewed, Resource)
    assert reviewed.review_status == "approved"


def test_reviewer_accepts_uniform_markdown_code_block_indentation() -> None:
    context = _context()
    resource = _resource(
        context,
        resource_type=ResourceType.CODING,
        content_format="python",
        content=(
            "```python\n"
            "    import numpy as np\n"
            "\n"
            "    def predict(values):\n"
            "        return (np.asarray(values) > 0).astype(int)\n"
            "\n"
            "    print(predict([-1, 1]))\n"
            "```\n\n"
            "该示例展示数组分类预测，并保留函数内部的相对缩进供语法审校。"
        ),
    )

    reviewed = asyncio.run(ReviewerAgent().review(resource, context))

    assert reviewed.review_status == "approved"


def test_reviewer_still_rejects_relative_python_indentation_error() -> None:
    context = _context()
    resource = _resource(
        context,
        resource_type=ResourceType.CODING,
        content_format="python",
        content=(
            "```python\n"
            "import numpy as np\n"
            "    print(np.asarray([1, 2]))\n"
            "```\n\n"
            "该示例故意保留单行错误缩进，用于确认审校不会放宽 Python 语法标准。"
        ),
    )

    reviewed = asyncio.run(ReviewerAgent().review(resource, context))

    assert reviewed.review_status == "needs_revision"
    assert "unexpected indent" in reviewed.personalization_reason


def test_reviewer_marks_placeholder_content_for_revision() -> None:
    context = _context()
    resource = _resource(
        context,
        content=(
            "# 梯度下降\n\n这里先说明目标函数与梯度的关系。"
            "TODO：在此处实现完整算法，并补充足够的验证案例和结论。"
        ),
    )

    reviewed = asyncio.run(ReviewerAgent().review(resource, context))

    assert reviewed.review_status == "needs_revision"
    assert "占位符" in reviewed.personalization_reason


def test_reviewer_rejects_unsafe_content() -> None:
    context = _context()
    resource = _resource(
        context,
        content=(
            "# 不安全示例\n\n这段材料要求生成恶意代码并实施入侵，"
            "其余文字只用于保证资源长度达到完整性检查要求。"
        ),
    )

    reviewed = asyncio.run(ReviewerAgent().review(resource, context))

    assert reviewed.review_status == "rejected"
    assert "审校拒绝" in reviewed.personalization_reason


@pytest.mark.parametrize(
    ("resource_type", "content_format", "content"),
    [
        (
            ResourceType.MIND_MAP,
            "mermaid",
            "这是一段没有 Mermaid 图类型声明的普通文字，内容足够长但无法作为思维导图渲染。",
        ),
        (
            ResourceType.CODING,
            "python",
            "```python\ndef broken(:\n    pass\n```\n这段代码存在明确语法错误，无法作为可运行案例。",
        ),
        (
            ResourceType.QUIZ,
            "json",
            json.dumps(
                {
                    "questions": [
                        {
                            "type": "single_choice",
                            "question": "以下哪项正确？",
                            "options": ["A. 选项甲", "B. 选项乙"],
                            "answer": "Z",
                            "explanation": "答案必须对应已有选项。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ),
    ],
)
def test_reviewer_detects_resource_format_problems(
    resource_type: ResourceType,
    content_format: str,
    content: str,
) -> None:
    context = _context()
    resource = _resource(
        context,
        resource_type=resource_type,
        content=content,
        content_format=content_format,
    )

    reviewed = asyncio.run(ReviewerAgent().review(resource, context))

    assert reviewed.review_status == "needs_revision"
