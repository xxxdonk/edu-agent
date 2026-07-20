from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.schemas import StudentProfile


EducationStage = Literal[
    "primary_school",
    "middle_school",
    "high_school",
    "vocational",
    "undergraduate",
    "postgraduate",
    "professional",
    "general_interest",
    "unknown",
]
SubjectFamily = Literal[
    "language",
    "mathematics",
    "natural_science",
    "social_science",
    "engineering",
    "computer_science",
    "arts",
    "business_economics",
    "medicine_health",
    "law",
    "interdisciplinary",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class SubjectContext:
    education_stage: EducationStage = "unknown"
    subject_name: str = ""
    subject_family: SubjectFamily = "unknown"
    grade_or_level: str = ""
    topic: str = ""
    learning_goal: str = ""
    exam_or_project: str = ""
    preferred_style: str = ""
    time_budget: int | None = None
    confidence: float = 0.0


_SUBJECT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("概率论与数理统计", ("概率论与数理统计", "概率统计")),
    ("计算机组成原理", ("计算机组成原理", "计组")),
    ("自动控制原理", ("自动控制原理", "自控")),
    ("中国近现代史纲要", ("中国近现代史纲要", "近现代史纲要")),
    ("马克思主义基本原理", ("马克思主义基本原理", "马原")),
    ("自然语言处理", ("自然语言处理", "NLP")),
    ("计算机视觉", ("计算机视觉", "CV")),
    ("机器学习", ("机器学习基础", "机器学习", "machine learning", "ML")),
    ("嵌入式系统", ("嵌入式系统", "嵌入式", "STM32")),
    ("高等数学", ("高等数学", "高数")),
    ("线性代数", ("线性代数", "线代")),
    ("高中数学", ("高中阶段数学", "高中数学")),
    ("高中语文", ("高中语文",)),
    ("高中英语", ("高中英语",)),
    ("高中物理", ("高中物理",)),
    ("高中化学", ("高中化学",)),
    ("高中生物", ("高中生物",)),
    ("高中历史", ("高中历史",)),
    ("高中地理", ("高中地理",)),
    ("高中政治", ("高中政治",)),
    ("初中数学", ("初中数学",)),
    ("初中英语", ("初中英语",)),
    ("初中历史", ("初中历史",)),
    ("小学数学", ("小学数学",)),
    ("大学英语", ("大学英语四级", "大学英语六级", "大学英语", "英语四级", "英语六级", "CET-4", "CET-6")),
    ("大学物理", ("大学物理",)),
    ("大学化学", ("大学化学",)),
    ("离散数学", ("离散数学",)),
    ("数据结构", ("数据结构",)),
    ("计算机网络", ("计算机网络",)),
    ("操作系统", ("操作系统",)),
    ("数据库", ("数据库",)),
    ("软件工程", ("软件工程",)),
    ("深度学习", ("深度学习",)),
    ("C语言", ("C语言", "C 语言")),
    ("Java", ("Java",)),
    ("Python", ("Python",)),
    ("算法", ("算法",)),
    ("电路", ("电路",)),
    ("模拟电子技术", ("模拟电子技术", "模电")),
    ("数字电子技术", ("数字电子技术", "数电")),
    ("信号与系统", ("信号与系统",)),
    ("单片机", ("单片机",)),
    ("通信原理", ("通信原理",)),
    ("工程力学", ("工程力学",)),
    ("机械设计", ("机械设计",)),
    ("经济学", ("经济学",)),
    ("管理学", ("管理学",)),
    ("心理学", ("心理学",)),
    ("法学基础", ("法学基础", "法学")),
    ("信息技术", ("信息技术",)),
    ("通用技术", ("通用技术",)),
    ("道德与法治", ("道德与法治",)),
    ("语文", ("语文",)),
    ("数学", ("数学",)),
    ("英语", ("英语",)),
    ("物理", ("物理",)),
    ("化学", ("化学",)),
    ("生物", ("生物",)),
    ("政治", ("政治",)),
    ("历史", ("历史",)),
    ("地理", ("地理",)),
    ("绘画", ("画画", "绘画", "美术")),
    ("音乐", ("音乐",)),
)


def infer_subject_context(text: str, *, current_course: str | None = None) -> SubjectContext:
    normalized = text.strip()
    stage, grade = _education_stage(normalized)
    candidates: list[tuple[int, int, str]] = []
    for canonical, aliases in _SUBJECT_ALIASES:
        for alias in aliases:
            for match in re.finditer(re.escape(alias), normalized, flags=re.IGNORECASE):
                candidates.append((match.start(), match.end(), canonical))
    specific_candidates = [
        candidate
        for candidate in candidates
        if not any(
            other[0] <= candidate[0]
            and candidate[1] <= other[1]
            and (other[1] - other[0]) > (candidate[1] - candidate[0])
            for other in candidates
        )
    ]
    subject = max(
        specific_candidates,
        default=(-1, -1, ""),
        key=lambda item: (_course_intent_score(normalized, item[0]), item[0]),
    )[2]
    subject = _apply_school_stage(subject, stage)
    if not subject and current_course:
        subject = current_course
    family = subject_family(subject)
    topic = _topic_hint(normalized, subject)
    confidence = 0.9 if candidates else (0.62 if subject else 0.35 if stage != "unknown" else 0.0)
    return SubjectContext(
        education_stage=stage,
        subject_name=subject,
        subject_family=family,
        grade_or_level=grade,
        topic=topic,
        exam_or_project=_exam_or_project(normalized),
        confidence=confidence,
    )


def subject_context_from_profile(profile: StudentProfile) -> SubjectContext:
    course = profile.course.value or ""
    major = profile.major.value or ""
    combined = " ".join(
        [
            major,
            course,
            *profile.learning_goals.value,
            *profile.weak_topics.value,
        ]
    )
    inferred = infer_subject_context(combined, current_course=course)
    return SubjectContext(
        education_stage=inferred.education_stage,
        subject_name=course or inferred.subject_name,
        subject_family=subject_family(course or inferred.subject_name),
        grade_or_level=inferred.grade_or_level,
        topic=(profile.weak_topics.value or [course or "当前学习主题"])[0],
        learning_goal="、".join(profile.learning_goals.value),
        exam_or_project=inferred.exam_or_project,
        preferred_style=profile.cognitive_style.value or "",
        time_budget=(profile.time_budget.value.minutes_per_day if profile.time_budget.value else None),
        confidence=max(inferred.confidence, profile.course.confidence),
    )


def subject_family(subject_name: str) -> SubjectFamily:
    name = subject_name.casefold()
    if any(token in name for token in ("语文", "英语", "语言", "写作", "阅读")):
        return "language"
    if any(token in name for token in ("数学", "概率", "统计", "线性代数", "高数")):
        return "mathematics"
    if any(token in name for token in ("物理", "化学", "生物")):
        return "natural_science"
    if any(token in name for token in ("历史", "地理", "政治", "道德", "马克思")):
        return "social_science"
    if any(token in name for token in ("java", "python", "c语言", "数据结构", "算法", "计算机", "数据库", "软件", "机器学习", "深度学习", "视觉", "自然语言处理")):
        return "computer_science"
    if any(token in name for token in ("电路", "电子", "信号", "控制", "嵌入式", "单片机", "通信", "工程", "机械")):
        return "engineering"
    if any(token in name for token in ("绘画", "美术", "音乐", "艺术")):
        return "arts"
    if any(token in name for token in ("经济", "管理", "商业", "金融", "会计")):
        return "business_economics"
    if any(token in name for token in ("医学", "护理", "健康", "药学")):
        return "medicine_health"
    if any(token in name for token in ("法学", "法律")):
        return "law"
    return "unknown"


def is_course_switch(previous_course: str | None, text: str) -> tuple[bool, SubjectContext]:
    context = infer_subject_context(text)
    if not previous_course or not context.subject_name:
        return False, context
    changed = context.subject_name.casefold() != previous_course.strip().casefold()
    explicit_switch = bool(
        re.search(
            r"改学|转学|换成|切换到|课程是|正在(?:学习|学)|想(?:学习|学|提高)|要(?:学习|学|提高)|准备|复习",
            text,
            flags=re.IGNORECASE,
        )
    )
    return changed and explicit_switch, context


def stage_display(context: SubjectContext) -> str | None:
    if context.grade_or_level:
        return context.grade_or_level
    return {
        "primary_school": "小学",
        "middle_school": "初中",
        "high_school": "高中",
        "vocational": "职业教育",
        "undergraduate": "大学本科",
        "postgraduate": "研究生",
        "professional": "职业学习",
    }.get(context.education_stage)


def is_machine_learning_subject(subject_name: str) -> bool:
    return "机器学习" in subject_name or "machine learning" in subject_name.casefold()


def _education_stage(text: str) -> tuple[EducationStage, str]:
    grade_patterns = (
        ("high_school", r"高[一二三123]", ""),
        ("middle_school", r"初[一二三123]", ""),
        ("primary_school", r"[一二三四五六123456]年级", "小学"),
    )
    for stage, pattern, prefix in grade_patterns:
        match = re.search(pattern, text)
        if match:
            grade = match.group()
            return stage, f"{prefix}{grade}" if prefix else grade
    stage_keywords: tuple[tuple[EducationStage, tuple[str, ...]], ...] = (
        ("high_school", ("高中", "高考")),
        ("middle_school", ("初中", "中考")),
        ("primary_school", ("小学",)),
        ("vocational", ("职高", "中专", "高职", "职业院校")),
        ("postgraduate", ("研究生", "硕士", "博士")),
        ("undergraduate", ("大学生", "本科", "大一", "大二", "大三", "大四", "大学")),
        ("professional", ("工作", "岗位", "职业技能", "转行", "面试")),
        ("general_interest", ("兴趣", "爱好")),
    )
    for stage, keywords in stage_keywords:
        if any(keyword in text for keyword in keywords):
            return stage, ""
    return "unknown", ""


def _apply_school_stage(subject: str, stage: EducationStage) -> str:
    if subject not in {"语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治"}:
        return subject
    prefix = {"primary_school": "小学", "middle_school": "初中", "high_school": "高中"}.get(stage)
    return f"{prefix}{subject}" if prefix else subject


def _topic_hint(text: str, subject: str) -> str:
    known_topics = (
        "函数", "数列", "极限", "矩阵", "阅读理解", "写作", "力学", "有机化学",
        "二叉树", "存储系统", "根轨迹", "频率响应", "中断", "逻辑回归",
    )
    found = [topic for topic in known_topics if topic in text and topic not in subject]
    return "、".join(found[:3])


def _exam_or_project(text: str) -> str:
    for keyword in ("高考", "中考", "期末考试", "期末", "月考", "四级", "六级", "考试", "项目", "面试"):
        if keyword in text:
            return keyword
    return ""


def _course_intent_score(text: str, start: int) -> int:
    prefix = text[max(0, start - 14) : start]
    return 1 if re.search(
        r"(?:课程是|正在(?:学习|学)|开始(?:学习|学)|想(?:学习|学)|要学|改学|转学|切换到|准备|复习)\s*$",
        prefix,
        flags=re.IGNORECASE,
    ) else 0
