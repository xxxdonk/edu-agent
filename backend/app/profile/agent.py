from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas.common import Difficulty, utc_now
from app.schemas.profile import (
    FieldEvidence,
    ProfileChatRequest,
    ProfileChatResponse,
    ProfileField,
    StudentProfile,
    TimeBudget,
)


class ProfileAgent:
    """Day-1 input-dependent heuristic adapter; replace with structured LLM extraction on Day 2."""

    mode = "development_heuristic"
    _required_dimensions = (
        "major",
        "knowledge_level",
        "learning_goals",
        "weak_topics",
        "cognitive_style",
        "time_budget",
    )

    def extract(
        self,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> ProfileChatResponse:
        user_messages = [message for message in request.messages if message.role == "user"]
        transcript = "\n".join(message.content for message in user_messages)

        major = self._first_group(
            transcript,
            (
                r"(?:专业是|主修|学的是)\s*([^，。,.；;\n]{2,30})",
                r"我是\s*([^，。,.；;\n]{2,20})专业",
            ),
        )
        course = self._first_group(
            transcript,
            (
                r"(?:课程是|正在学习|正在学|想学习|想学|学习)\s*[《“\"]?([^》”\"，。,.；;\n]{2,30})",
            ),
        )
        level = self._extract_level(transcript)
        goals = self._extract_phrases(
            transcript,
            ("目标是", "希望", "我想", "想要", "最后能", "为了"),
        )
        weak_topics = self._extract_weak_topics(transcript)
        history = self._extract_phrases(transcript, ("学过", "接触过", "完成过"))
        cognitive_style = self._extract_cognitive_style(transcript)
        language = self._extract_language(transcript)
        resources = self._extract_resource_preferences(transcript)
        time_budget = self._extract_time_budget(transcript)

        evaluation_evidence: list[FieldEvidence] = []
        if request.evaluation_summary:
            evaluation_evidence.append(
                FieldEvidence(source="evaluation", quote=request.evaluation_summary[:500])
            )
            weak_topics = self._merge_lists(
                weak_topics,
                self._extract_weak_topics(request.evaluation_summary),
            )

        profile = StudentProfile(
            student_id=request.student_id,
            version=(previous.version + 1) if previous else 1,
            major=self._scalar_field("major", major, previous, user_messages),
            course=self._course_field(course, previous, user_messages),
            knowledge_level=self._scalar_field(
                "knowledge_level",
                level,
                previous,
                user_messages,
                evidence_source="inference",
                confidence=0.72,
            ),
            learning_goals=self._list_field("learning_goals", goals, previous, user_messages),
            weak_topics=self._list_field(
                "weak_topics",
                weak_topics,
                previous,
                user_messages,
                extra_evidence=evaluation_evidence,
            ),
            learning_history=self._list_field(
                "learning_history", history, previous, user_messages
            ),
            cognitive_style=self._scalar_field(
                "cognitive_style",
                cognitive_style,
                previous,
                user_messages,
                evidence_source="inference",
                confidence=0.68,
            ),
            language_preference=self._scalar_field(
                "language_preference", language, previous, user_messages
            ),
            resource_preference=self._list_field(
                "resource_preference",
                resources,
                previous,
                user_messages,
                evidence_source="inference",
                confidence=0.68,
            ),
            time_budget=self._time_budget_field(
                time_budget, previous, user_messages, transcript
            ),
            evidence=[],
            confidence=0.0,
            updated_at=utc_now(),
        )
        profile.evidence = self._consolidated_evidence(
            profile,
            self._profile_evidence(user_messages, evaluation_evidence),
        )
        profile.confidence = self._overall_confidence(profile)
        missing = self._missing_dimensions(profile)
        return ProfileChatResponse(
            profile=profile,
            missing_dimensions=missing,
            next_question=self._next_question(missing[0]) if missing else None,
            is_complete=not missing,
            extraction_mode=self.mode,
        )

    @staticmethod
    def _first_group(text: str, patterns: Iterable[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" 《》\"“”")
        return None

    @staticmethod
    def _extract_level(text: str) -> Difficulty | None:
        if any(
            keyword in text
            for keyword in ("零基础", "没学过", "初学", "入门", "刚开始", "才开始")
        ):
            return Difficulty.BEGINNER
        if any(keyword in text for keyword in ("熟练", "深入", "进阶", "做过项目")):
            return Difficulty.ADVANCED
        if any(keyword in text for keyword in ("有基础", "了解", "学过一些", "基础一般")):
            return Difficulty.INTERMEDIATE
        return None

    @staticmethod
    def _extract_phrases(text: str, markers: Iterable[str]) -> list[str]:
        results: list[str] = []
        for sentence in re.split(r"[。！？!?；;\n]", text):
            sentence = sentence.strip()
            positions = [sentence.find(marker) for marker in markers if marker in sentence]
            if sentence and positions:
                fragment = sentence[min(positions) :][:100]
                results.extend(
                    part.strip(" ，,")
                    for part in re.split(r"[，,]?(?:并且|同时|然后)", fragment)
                    if part.strip(" ，,")
                )
        return list(dict.fromkeys(results))[:5]

    @staticmethod
    def _extract_weak_topics(text: str) -> list[str]:
        results: list[str] = []
        patterns = (
            r"(?:不懂|不会|薄弱(?:的是)?|困难(?:的是)?|不熟悉)\s*([^，。,.；;\n]{2,30})",
            r"([^，。,.；;\n]{2,20})(?:比较薄弱|比较一般|较弱|欠缺|没掌握|总出错)",
        )
        for pattern in patterns:
            results.extend(match.strip() for match in re.findall(pattern, text))
        return list(dict.fromkeys(results))[:5]

    @staticmethod
    def _extract_cognitive_style(text: str) -> str | None:
        if any(keyword in text for keyword in ("图示", "画图", "可视化", "思维导图")):
            return "visual"
        if any(keyword in text for keyword in ("动手", "边做边学", "代码实践", "做题")):
            return "practice_oriented"
        if any(keyword in text for keyword in ("原理", "推导", "理论")):
            return "theory_oriented"
        return None

    @staticmethod
    def _extract_language(text: str) -> str | None:
        if "英文" in text or "英语" in text:
            return "English"
        if "中文" in text or "汉语" in text:
            return "中文"
        return None

    @staticmethod
    def _extract_resource_preferences(text: str) -> list[str]:
        mapping = {
            "讲解文档": ("文档", "讲解"),
            "思维导图": ("思维导图", "图示", "可视化"),
            "分层练习题": ("练习", "做题", "题目"),
            "拓展阅读": ("阅读", "论文", "资料"),
            "代码实践案例": ("代码", "编程", "实践"),
        }
        return [name for name, keywords in mapping.items() if any(k in text for k in keywords)]

    @staticmethod
    def _extract_time_budget(text: str) -> TimeBudget | None:
        daily = re.search(
            r"每天\s*(?:大概|大约)?\s*(?:能|可以)?\s*(?:学习|投入)?\s*"
            r"(\d+(?:\.\d+)?)\s*(分钟|小时)",
            text,
        )
        weekly = re.search(r"每周\s*(\d+)\s*天", text)
        if not daily and not weekly:
            return None
        minutes = 30
        if daily:
            value = float(daily.group(1))
            minutes = round(value * 60) if daily.group(2) == "小时" else round(value)
        days = int(weekly.group(1)) if weekly else 5
        return TimeBudget(minutes_per_day=minutes, days_per_week=days)

    def _scalar_field(
        self,
        name: str,
        value: object | None,
        previous: StudentProfile | None,
        messages: list,
        evidence_source: str = "conversation",
        confidence: float = 0.78,
    ) -> ProfileField:
        if value is not None:
            return ProfileField(
                value=value,
                evidence=self._matching_evidence(
                    messages, value, source=evidence_source
                ),
                confidence=confidence,
            )
        if previous:
            return getattr(previous, name).model_copy(deep=True)
        return ProfileField(value=None, evidence=[], confidence=0.0)

    def _course_field(
        self,
        value: str | None,
        previous: StudentProfile | None,
        messages: list,
    ) -> ProfileField[str | None]:
        if value:
            return self._scalar_field("course", value, previous, messages)
        if previous:
            return previous.course.model_copy(deep=True)
        return ProfileField(
            value="机器学习基础",
            evidence=[
                FieldEvidence(
                    source="system_default",
                    quote="默认演示课程：《机器学习基础》",
                )
            ],
            confidence=0.55,
        )

    def _time_budget_field(
        self,
        value: TimeBudget | None,
        previous: StudentProfile | None,
        messages: list,
        transcript: str,
    ) -> ProfileField[TimeBudget | None]:
        if value is None:
            if previous:
                return previous.time_budget.model_copy(deep=True)
            return ProfileField(value=None, evidence=[], confidence=0.0)

        evidence = self._matching_evidence(messages, value, source="conversation")
        inferred_defaults: list[str] = []
        if "每天" not in transcript:
            inferred_defaults.append("未提供每日时长，默认30分钟")
        if "每周" not in transcript:
            inferred_defaults.append("未提供每周学习天数，默认5天")
        evidence.extend(
            FieldEvidence(source="system_default", quote=description)
            for description in inferred_defaults
        )
        return ProfileField(
            value=value,
            evidence=evidence,
            confidence=0.65 if inferred_defaults else 0.78,
        )

    def _list_field(
        self,
        name: str,
        values: list[str],
        previous: StudentProfile | None,
        messages: list,
        extra_evidence: list[FieldEvidence] | None = None,
        evidence_source: str = "conversation",
        confidence: float = 0.78,
    ) -> ProfileField[list[str]]:
        old = getattr(previous, name) if previous else None
        merged = self._merge_lists(old.value if old else [], values)
        evidence = list(old.evidence) if old else []
        if values:
            evidence.extend(
                self._matching_evidence(
                    messages, values[0], source=evidence_source
                )
            )
        evidence.extend(extra_evidence or [])
        evidence = self._deduplicate_evidence(evidence)
        field_confidence = (
            confidence if values or extra_evidence else (old.confidence if old else 0.0)
        )
        return ProfileField(value=merged, evidence=evidence, confidence=field_confidence)

    @staticmethod
    def _deduplicate_evidence(evidence_items: list[FieldEvidence]) -> list[FieldEvidence]:
        unique: list[FieldEvidence] = []
        seen: set[tuple[str, str, str | None]] = set()
        for evidence in evidence_items:
            key = (evidence.source, evidence.quote, evidence.message_id)
            if key not in seen:
                unique.append(evidence)
                seen.add(key)
        return unique

    @staticmethod
    def _merge_lists(left: list[str], right: list[str]) -> list[str]:
        return list(dict.fromkeys([*left, *right]))[:10]

    @staticmethod
    def _matching_evidence(
        messages: list, value: object, *, source: str
    ) -> list[FieldEvidence]:
        needle = str(value.value if isinstance(value, Difficulty) else value)
        for message in reversed(messages):
            if needle in message.content or needle in {"beginner", "intermediate", "advanced"}:
                return [
                    FieldEvidence(
                        source=source,
                        quote=message.content[:500],
                        message_id=message.message_id,
                    )
                ]
        if messages:
            message = messages[-1]
            return [
                FieldEvidence(
                    source=source,
                    quote=message.content[:500],
                    message_id=message.message_id,
                )
            ]
        return []

    @staticmethod
    def _consolidated_evidence(
        profile: StudentProfile,
        base_evidence: list[FieldEvidence],
    ) -> list[FieldEvidence]:
        field_names = (
            "major",
            "course",
            "knowledge_level",
            "learning_goals",
            "weak_topics",
            "learning_history",
            "cognitive_style",
            "language_preference",
            "resource_preference",
            "time_budget",
        )
        combined = list(base_evidence)
        for field_name in field_names:
            combined.extend(getattr(profile, field_name).evidence)
        return ProfileAgent._deduplicate_evidence(combined)

    @staticmethod
    def _profile_evidence(
        messages: list, evaluation_evidence: list[FieldEvidence]
    ) -> list[FieldEvidence]:
        conversation = [
            FieldEvidence(
                source="conversation",
                quote=message.content[:500],
                message_id=message.message_id,
            )
            for message in messages[-10:]
        ]
        return [*conversation, *evaluation_evidence]

    def _missing_dimensions(self, profile: StudentProfile) -> list[str]:
        missing: list[str] = []
        for name in self._required_dimensions:
            field = getattr(profile, name)
            if field.value is None or field.value == [] or field.confidence < 0.5:
                missing.append(name)
        return missing

    @staticmethod
    def _overall_confidence(profile: StudentProfile) -> float:
        names = (
            "major",
            "course",
            "knowledge_level",
            "learning_goals",
            "weak_topics",
            "learning_history",
            "cognitive_style",
            "language_preference",
            "resource_preference",
            "time_budget",
        )
        return round(sum(getattr(profile, name).confidence for name in names) / len(names), 3)

    @staticmethod
    def _next_question(dimension: str) -> str:
        questions = {
            "major": "你目前的专业或主要学习方向是什么？",
            "knowledge_level": "你之前接触过这门课程吗？可以举例说明目前的程度。",
            "learning_goals": "你希望通过这门课程具体达成什么目标？",
            "weak_topics": "目前哪些概念或题型让你最困惑？",
            "cognitive_style": "你更喜欢图示理解、原理推导，还是边做边学？",
            "time_budget": "你每周能学习几天、每天大约投入多少分钟？",
        }
        return questions[dimension]
