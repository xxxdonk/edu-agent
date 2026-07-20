from __future__ import annotations

import json
from uuid import uuid4

from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import SubjectContext, subject_context_from_profile


def should_use_cross_subject(context: SharedAgentContext) -> bool:
    subject = subject_context_from_profile(context.profile)
    return "机器学习" not in subject.subject_name


def explanation_resource(
    context: SharedAgentContext,
    topic: str,
    difficulty: str,
    references: list[SourceReference],
) -> Resource:
    subject = subject_context_from_profile(context.profile)
    course = subject.subject_name or "当前学习主题"
    goal = subject.learning_goal or f"掌握{course}的当前内容"
    weak = "、".join(context.profile.weak_topics.value or [topic])
    structure = _family_structure(subject)
    formula = _formula_section(subject, topic)
    content = f"""# {topic} - 学科适配讲解

## 1. 本节学习目标
围绕“{goal}”，理解{topic}的核心概念，能完成基础辨析、典型任务和一次自我检查。

## 2. 为什么需要学习这一部分
当前课程是{course}，薄弱点集中在{weak}。本节将内容拆成“{structure}”，避免只记结论。

## 3. 前置知识快速回顾
先列出已经确认的概念、符号或背景，再标记仍不确定的部分；没有证据的信息不作为已掌握内容。

## 4. 核心概念
用“是什么、为什么、何时使用、如何验证”四个问题理解{topic}，并为每个结论准备一个正例和一个反例。

## 5. 原理与公式
{formula}

## 6. 分步方法
1. 读清任务，圈出条件与目标。
2. 回忆相关概念，选择匹配的方法。
3. 分步骤执行并写出依据。
4. 检查条件、过程和最终表达。
5. 把错误归类到概念、方法或表达。

## 7. 完整示例
选择一个与{course}当前章节一致的典型任务：先复述条件，再说明采用的方法，完成关键步骤，最后用反例、代入或材料证据检查结论。示例的完成标准是每一步都能回答“依据是什么”。

## 8. 常见错误
1. **目标识别错误**：没读清目标就直接作答。
2. **条件使用错误**：记住结论却忽略适用条件。
3. **过程不完整**：跳过关键步骤，导致结果无法检查。
4. **复盘不足**：只看答案，不记录错误原因。
5. **跨学科套用**：把旧课程的方法机械套到当前课程。

## 9. 快速自检
1. 你能用一句话解释{topic}吗？
2. 你能指出一种常见错误并修正吗？
3. 你能独立完成一道同类任务并说明依据吗？

## 10. FAQ
**Q1：需要先背结论吗？** 先理解适用条件，再通过练习记忆。

**Q2：看懂例题等于会做吗？** 不等于，需要合上答案独立重做。

**Q3：卡住时怎么办？** 回到条件、目标和已知方法逐项排查。

**Q4：如何整理错题？** 记录错误类型、正确依据和一道变式练习。

**Q5：什么时候进入下一步？** 当你能解释概念并稳定完成基础任务时。

## 11. 本节总结
{topic}的学习主线是“理解概念 -> 识别条件 -> 选择方法 -> 完成任务 -> 检查与复盘”。

## 12. 下一步建议
先查看思维导图建立结构，再完成应用实践和分层练习，最后根据错题更新画像与学习路径。
"""
    return _resource(ResourceType.EXPLANATION, f"{topic} 课程讲解", content, "markdown", context, topic, difficulty, references)


def mind_map_resource(
    context: SharedAgentContext,
    topic: str,
    difficulty: str,
    references: list[SourceReference],
) -> Resource:
    subject = subject_context_from_profile(context.profile)
    nodes = _mind_map_nodes(subject)
    lines = ["mindmap", f"  root(({_safe_mermaid(topic)}))"]
    for parent, children in nodes:
        lines.append(f"    {_safe_mermaid(parent)}")
        lines.extend(f"      {_safe_mermaid(child)}" for child in children)
    return _resource(
        ResourceType.MIND_MAP,
        f"{topic} 思维导图",
        "\n".join(lines) + "\n",
        "mermaid",
        context,
        topic,
        difficulty,
        references,
    )


def quiz_resource(
    context: SharedAgentContext,
    topic: str,
    difficulty: str,
    references: list[SourceReference],
) -> Resource:
    subject = subject_context_from_profile(context.profile)
    course = subject.subject_name or "当前学习主题"
    family_focus = _family_structure(subject)
    resource_id = str(uuid4())
    basic = _basic_questions(subject, topic, course)
    written = [
        (f"请用自己的话说明{topic}的核心概念和适用条件。", f"回答应包含{topic}是什么、何时使用以及至少一个检查方法。", "考查概念理解与边界意识。"),
        (f"请按顺序写出完成一个{course}典型任务的步骤。", "读清条件与目标，回忆概念，选择方法，分步完成，检查并复盘。", f"考查{family_focus}能否形成完整流程。"),
        (f"针对薄弱点“{'、'.join(context.profile.weak_topics.value or [topic])}”，设计两项可检查的练习。", "安排一道基础辨析和一道综合应用，分别记录依据、结果与错误原因。", "练习应与画像薄弱点直接对应。"),
    ]
    challenge = [
        (f"为“{subject.learning_goal or '完成当前学习目标'}”设计一周的{course}学习任务和验收标准。", "按概念、示例、练习、复盘分配时间；验收包括概念复述、任务正确率和错题改正。", "综合考查计划、实践和评价。"),
        (f"遇到一道无法完成的{topic}综合任务时，你会如何定位问题？", "依次检查概念、条件识别、方法选择、执行过程和表达，再针对首个断点补练。", "用可观察证据定位问题，避免盲目重复。"),
        (f"比较两种学习{topic}的方法，并说明如何选择。", "在相同任务和时间下比较理解程度、正确率与复盘质量，选择更符合目标和偏好的方法。", "选择应依据同一标准下的学习证据。"),
    ]
    questions: list[dict[str, object]] = []
    for index, (question, options, answer, explanation) in enumerate(basic, 1):
        questions.append({"id": f"{resource_id}::q{index}", "type": "single_choice", "level": "basic", "question": question, "options": options, "answer": answer, "explanation": explanation})
    for offset, (question, answer, explanation) in enumerate(written, 4):
        questions.append({"id": f"{resource_id}::q{offset}", "type": "short_answer", "level": "intermediate", "question": question, "answer": answer, "explanation": explanation})
    for offset, (question, answer, explanation) in enumerate(challenge, 7):
        questions.append({"id": f"{resource_id}::q{offset}", "type": "comprehensive", "level": "advanced", "question": question, "answer": answer, "explanation": explanation})
    content = json.dumps({"topic": topic, "difficulty": difficulty, "questions": questions}, ensure_ascii=False, indent=2)
    return Resource(
        resource_id=resource_id,
        resource_type=ResourceType.QUIZ,
        title=f"{topic} 分层练习题",
        content=content,
        content_format="json",
        target_topic=topic,
        difficulty=Difficulty(difficulty),
        personalization_reason=_reason(context),
        source_references=references,
        review_status="pending",
    )


def reading_resource(
    context: SharedAgentContext,
    topic: str,
    difficulty: str,
    references: list[SourceReference],
) -> Resource:
    subject = subject_context_from_profile(context.profile)
    course = subject.subject_name or "当前学习主题"
    source_lines = [
        f"- {ref.title}（{ref.locator}）" for ref in references if ref.source_id != "general-model"
    ] or ["- 本地知识库未命中相关课程资料，本资源由通用模型生成。"]
    terms = ["核心概念", "适用条件", "典型任务", "分析框架", "关键步骤", "检查方法", "常见误区", "证据", "变式练习", "学习评价"]
    glossary = "\n".join(f"- {term}：在{course}学习中用于组织和检查{topic}的要点" for term in terms)
    questions = "\n".join(f"{index}. {question}" for index, question in enumerate([
        f"{topic}要解决的核心问题是什么？", "哪些条件会影响方法选择？", "如何检查结论是否成立？", "一个常见误区是什么？", "怎样设计一道变式练习？", "如何用学习证据决定下一步？",
    ], 1))
    content = f"""# {topic} 拓展阅读

## 1. 阅读目标
围绕{course}建立{topic}的背景、方法比较与应用视角，不重复课程讲解正文。

## 2. 10 分钟快速阅读
先找出主题、关键概念和结论，再标记支持结论的条件或材料。读完后用三句话复述主要内容。

## 3. 20 至 40 分钟深入阅读
沿“背景 -> 问题 -> 方法 -> 证据 -> 局限 -> 应用”阅读，比较至少两种处理方式，并说明它们各自适合的任务。

## 4. 项目阅读路线
1. 明确{topic}在{course}中的位置。
2. 整理核心概念和适用条件。
3. 比较一个正例与一个反例。
4. 完成一项材料、题目或作品分析。

## 5. 关键术语表
{glossary}

## 6. 阅读检查问题
{questions}

## 7. 推荐实践
制作一页阅读记录：左侧写核心观点，中间写支持证据，右侧写疑问和可验证的下一步练习。

## 8. 真实 RAG 来源
{chr(10).join(source_lines)}
"""
    return _resource(ResourceType.READING, f"{topic} 拓展阅读材料", content, "markdown", context, topic, difficulty, references)


def practice_resource(
    context: SharedAgentContext,
    topic: str,
    difficulty: str,
    references: list[SourceReference],
) -> Resource:
    subject = subject_context_from_profile(context.profile)
    computational = subject.subject_family in {"computer_science", "mathematics", "natural_science", "engineering"}
    if computational:
        code, expected_output = _computational_example(subject, topic)
        content = f"""# {topic} - 计算与实验实践

## 1. 实验目标
用一个可复现的小实验验证{topic}中的关系，并记录输入、过程、输出和结论。

## 2. 环境说明
- Python 3.10+
- 仅使用标准库
- 不访问外网，不自动安装依赖

## 3. 输入数据说明
使用一组可直接阅读的小型数值作为输入，不读取本地文件，也不包含个人信息。

## 4. 分步骤任务
1. 理解输入与输出。
2. 手算一个小样本。
3. 运行代码并核对。
4. 修改规则完成变式实验。

## 5. 完整 Python 代码
```python
{code}
```

## 6. 预期输出
{expected_output}

## 7. TODO 练习
1. 增加一组边界输入。
2. 将核心计算封装为函数。
3. 输出一项用于检查结果的统计量。

## 8. 调试提示
1. 先检查输入类型。
2. 打印中间结果定位步骤。
3. 用手算结果核对小样本。
4. 一次只修改一个因素。

## 9. 进阶挑战
1. 比较两种计算方法的结果。
2. 设计异常输入并解释处理策略。

## 10. 反思问题
1. 实验验证了什么？
2. 哪些结论不能由该小实验推出？
3. 如何让结果更容易复现？
"""
        title = f"{topic} 计算与实验实践"
        content_format = "python"
    else:
        family_task = {
            "language": "完成阅读批注、仿写或表达任务",
            "social_science": "制作时间线或材料因果分析表",
            "arts": "完成作品赏析、技法模仿与自评",
        }.get(subject.subject_family, "完成一项与当前主题一致的应用任务")
        content = f"""# {topic} - 应用实践任务

## 1. 任务目标
{family_task}，把{topic}从“看懂”转化为可检查的学习产出。

## 2. 准备材料
- 当前课程讲解与思维导图
- 一页纸或电子笔记
- 自评清单

## 3. 分步骤任务
1. 用三句话概括{topic}。
2. 选择一段材料、一道题或一个作品进行标注。
3. 按“依据 -> 分析 -> 结论”完成输出。
4. 对照完成标准修改一次。

## 4. 产出要求
提交一份结构化笔记或短文，包含主题、证据、分析、结论和一个仍待解决的问题。

## 5. 自评清单
- 内容与当前课程一致。
- 每个结论都有依据。
- 已修正至少一个表达或分析问题。
- 没有强行加入无关代码。

## 6. 进阶挑战
换一份材料重复任务，并比较两次输出在证据和表达上的差异。
"""
        title = f"{topic} 应用实践任务"
        content_format = "markdown"
    return _resource(ResourceType.CODING, title, content, content_format, context, topic, difficulty, references)


def _resource(resource_type: ResourceType, title: str, content: str, content_format: str, context: SharedAgentContext, topic: str, difficulty: str, references: list[SourceReference]) -> Resource:
    return Resource(resource_id=str(uuid4()), resource_type=resource_type, title=title, content=content, content_format=content_format, target_topic=topic, difficulty=Difficulty(difficulty), personalization_reason=_reason(context), source_references=references, review_status="pending")


def _reason(context: SharedAgentContext) -> str:
    profile = context.profile
    return f"当前课程：{profile.course.value or '当前学习主题'}；薄弱点：{'、'.join(profile.weak_topics.value or ['尚待确认'])}；学习目标：{'、'.join(profile.learning_goals.value or ['完成当前学习任务'])}"


def _family_structure(subject: SubjectContext) -> str:
    return {
        "mathematics": "定义、公式、推导、例题、解题步骤与易错点",
        "natural_science": "概念、规律、公式、实验、例题与易错点",
        "language": "背景、基础知识、阅读方法、表达练习与纠错",
        "social_science": "时间线、框架、原因、影响、材料分析与答题表达",
        "computer_science": "原理、结构、流程、示例、实践与调试",
        "engineering": "理论、模型、系统结构、分析、实验设计与应用",
        "arts": "基础元素、作品分析、技法、模仿、创作与评价",
    }.get(subject.subject_family, "基础概念、核心方法、示例、练习与评价")


def _formula_section(subject: SubjectContext, topic: str) -> str:
    if "自动控制" in subject.subject_name:
        return (
            r"单位负反馈系统的闭环传递函数可写为 "
            r"\(T(s)=\frac{G(s)}{1+G(s)H(s)}\)。根轨迹关注闭环特征方程 "
            r"\(1+G(s)H(s)=0\) 的根随参数变化的位置；频率响应则考察 "
            r"\(G(j\omega)\) 的幅值与相位。"
        )
    if subject.subject_family == "mathematics":
        return (
            r"以函数变化为例，可写作 \(y=f(x)\)。其中 \(x\) 是自变量，"
            r"\(y\) 是函数值；等差数列可写为 \(a_n=a_1+(n-1)d\)。"
            "解题时要先确认定义域、变量关系与公式适用条件。"
        )
    return "本节不强行引入与学科无关的公式，重点使用该课程真实需要的概念和方法。"


def _basic_questions(
    subject: SubjectContext,
    topic: str,
    course: str,
) -> list[tuple[str, list[str], str, str]]:
    if "自动控制" in subject.subject_name:
        first = (
            "连续系统稳定时，闭环极点应位于复平面的哪个区域？",
            ["A. 左半平面", "B. 右半平面", "C. 仅在虚轴上", "D. 任意区域"],
            "A",
            "连续时间闭环系统的极点全部位于左半平面时才渐近稳定。",
        )
    elif "英语" in course:
        first = (
            "Which sentence is grammatically complete?",
            ["A. Because the test was difficult.", "B. She reviewed her notes before the test.", "C. While reading the article.", "D. To improve the final score."],
            "B",
            "B contains a complete subject and predicate; the other options are fragments.",
        )
    elif subject.subject_family == "mathematics":
        first = (
            "若函数 f(x)=x^2，则 f(3) 等于多少？",
            ["A. 3", "B. 6", "C. 9", "D. 12"],
            "C",
            "把 x=3 代入 f(x)=x^2，得到 f(3)=3^2=9。",
        )
    else:
        first = (
            f"学习{topic}时，以下哪种做法最可靠？",
            ["A. 先明确条件和目标，再选择方法", "B. 忽略条件直接套结论", "C. 只抄最终答案", "D. 用其他课程内容代替"],
            "A",
            "可靠学习从当前学科的条件、目标和方法出发。",
        )
    return [
        first,
        (f"检查一道{course}任务是否完成，最重要的是？", ["A. 字数越多越好", "B. 过程有依据且结论符合条件", "C. 使用复杂术语", "D. 与同学答案完全相同"], "B", "完成标准应可验证，并与题目条件一致。"),
        (f"关于{topic}错题复盘，哪一项正确？", ["A. 只记正确答案", "B. 删除所有旧记录", "C. 标记错误原因并完成变式练习", "D. 立刻更换课程"], "C", "错题复盘需要定位原因并通过变式验证改进。"),
    ]


def _computational_example(subject: SubjectContext, topic: str) -> tuple[str, str]:
    if "自动控制" in subject.subject_name:
        return (
            "import cmath\n\n"
            "frequencies = [0.1, 1.0, 10.0]\n"
            "for omega in frequencies:\n"
            "    response = 1 / (1 + 1j * omega)\n"
            "    magnitude = abs(response)\n"
            "    phase_deg = cmath.phase(response) * 180 / 3.141592653589793\n"
            "    print(f\"omega={omega:>4.1f}, |G(jw)|={magnitude:.4f}, phase={phase_deg:.2f} deg\")",
            "程序输出一阶系统在三个频率点的幅值和相位。频率升高时幅值减小、相位趋近 -90 度，可据此核对频率响应的基本趋势。",
        )
    if subject.subject_family == "mathematics" and any(
        marker in topic for marker in ("函数", "数列")
    ):
        return (
            "def arithmetic_term(first, difference, index):\n"
            "    return first + (index - 1) * difference\n\n"
            "for index in range(1, 6):\n"
            "    value = arithmetic_term(2, 3, index)\n"
            "    print(f\"a_{index}={value}\")",
            "程序依次输出等差数列 2、5、8、11、14，用于核对通项公式 a_n=a_1+(n-1)d。",
        )
    return (
        "values = [1, 2, 3, 4, 5]\n"
        "results = [value * value for value in values]\n"
        "for value, result in zip(values, results):\n"
        "    print(f\"input={value}, result={result}\")",
        f"程序逐行输出输入和计算结果。请把计算规则替换为{topic}中需要验证的公式或过程。",
    )


def _mind_map_nodes(subject: SubjectContext) -> list[tuple[str, list[str]]]:
    branches = {
        "mathematics": [("核心概念", ["定义", "性质"]), ("公式关系", ["变量含义", "适用条件"]), ("典型题型", ["基础题", "综合题"]), ("解题流程", ["读题", "推导", "检查"]), ("易错点", ["条件遗漏", "计算错误"]), ("学习评价", ["正确率", "错题复盘"])],
        "language": [("基础知识", ["词汇字词", "语法表达"]), ("文本理解", ["结构", "主题"]), ("阅读方法", ["信息定位", "证据分析"]), ("输出表达", ["写作", "口语"]), ("纠错复盘", ["内容", "表达"]), ("学习评价", ["理解", "运用"])],
        "social_science": [("基本概念", ["定义", "边界"]), ("时间框架", ["背景", "过程"]), ("因果分析", ["原因", "影响"]), ("材料分析", ["证据", "观点"]), ("答题表达", ["结构", "术语"]), ("学习评价", ["复述", "应用"])],
    }
    return branches.get(subject.subject_family, [("核心概念", ["定义", "条件"]), ("基本原理", ["关系", "方法"]), ("示例分析", ["输入", "过程", "结果"]), ("实践任务", ["准备", "执行", "检查"]), ("常见错误", ["概念", "方法"]), ("学习评价", ["练习", "复盘"])])


def _safe_mermaid(value: str) -> str:
    for character in '"\'`:：\\()[]{}':
        value = value.replace(character, " ")
    return " ".join(value.split()) or "当前学习主题"
