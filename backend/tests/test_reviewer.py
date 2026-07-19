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
            "# 线性模型基础\n\n## 学习目标\n解释输入、参数与输出。\n"
            "## 为什么需要学习\n用于完成分类项目。\n## 前置知识\n特征与标签。\n"
            "## 核心概念\n训练参数并验证泛化。\n## 原理与公式\n\\(J(w)=L(f_w(x),y)\\)。\n"
            "## 分步流程\n1. 划分数据。\n2. 训练验证。\n## 完整示例\n完成一个分类实验。\n"
            "## 常见错误\n1. **数据泄漏**：重新划分。\n2. **只看训练集**：检查验证集。\n"
            "3. **盲目调参**：固定基线。\n4. **忽略复现**：固定种子。\n"
            "## 快速自检\n为什么需要验证集？\n## FAQ\n"
            "**Q1：如何开始？** 建立基线。\n**Q2：如何验证？** 使用验证集。\n"
            "**Q3：如何调参？** 控制变量。\n**Q4：如何复现？** 固定种子。\n"
            "**Q5：如何改进？** 根据误差分析。\n## 本节总结\n训练与验证结合。\n"
            "## 下一步\n完成代码实验。"
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
            "# 代码实践\n\n## 实验目标\n完成数组分类。\n## 环境说明\nPython。\n"
            "## 输入数据\n整数数组。\n## 分步骤任务\n1. 定义函数。\n2. 输出结果。\n"
            "## 完整 Python 代码\n"
            "```python\n"
            "    import numpy as np\n"
            "\n"
            "    def predict(values):\n"
            "        return (np.asarray(values) > 0).astype(int)\n"
            "\n"
            "    print(predict([-1, 1]))\n"
            "```\n\n## 预期输出\n分类数组。\n## TODO 练习\n1. 调整阈值。\n2. 增加输入。\n3. 比较结果。\n"
            "## 调试提示\n检查输入、类型、缩进和输出。\n## 进阶挑战\n1. 指标统计。\n2. 多组输入。\n"
            "## 反思问题\n为什么需要验证？\n"
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
