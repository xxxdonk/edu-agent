from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable

from pydantic import ValidationError

from app.llm import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponseFormatError,
    LLMValidationError,
)
from app.llm.errors import safe_error_summary
from app.schemas.common import Difficulty, utc_now
from app.schemas.profile import (
    FieldEvidence,
    ProfileChatRequest,
    ProfileChatResponse,
    ProfileField,
    StudentProfile,
    TimeBudget,
)
from .models import ProfileExtractionDraft
from .prompts import PROFILE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class DevelopmentProfileAgent:
    """Input-dependent heuristic fallback used when structured LLM extraction is unavailable."""

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
            r"([^，。,.；;\n]{2,20}基础)(?:比较)?一般",
            r"([^，。,.；;\n]{2,20}?)(?:一直)?(?:没弄懂|不理解|不明白)",
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
    def _profile_field_names() -> tuple[str, ...]:
        return (
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

    @staticmethod
    def _consolidated_evidence(
        profile: StudentProfile,
        base_evidence: list[FieldEvidence],
    ) -> list[FieldEvidence]:
        combined = list(base_evidence)
        for field_name in DevelopmentProfileAgent._profile_field_names():
            combined.extend(getattr(profile, field_name).evidence)
        return DevelopmentProfileAgent._deduplicate_evidence(combined)

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
        names = DevelopmentProfileAgent._profile_field_names()
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


class ProfileAgent:
    """Structured LLM profile extraction with an explicit heuristic fallback."""

    _question_variants = {
        "major": (
            "你目前的专业或主要学习方向是什么？",
            "方便说说你现在主修什么，或主要往哪个方向学习吗？",
            "为了匹配学习内容，我还需要了解你的专业或学习方向。",
        ),
        "knowledge_level": (
            "你之前接触过这门课程吗？可以举例说明目前的程度。",
            "你对这门课目前大概掌握到什么程度？举个学过的例子也可以。",
            "为了安排起点，你可以简单说说已有基础或相关经验吗？",
        ),
        "learning_goals": (
            "你希望通过这门课程具体达成什么目标？",
            "学完这部分内容后，你最希望自己能够完成什么？",
            "这次学习对你来说，最重要的成果是什么？",
        ),
        "weak_topics": (
            "目前哪些概念或题型让你最困惑？",
            "学习过程中，你现在最容易卡在哪个知识点？",
            "如果只选一个最想补强的难点，会是哪一项？",
        ),
        "cognitive_style": (
            "你更喜欢图示理解、原理推导，还是边做边学？",
            "哪种学习方式对你最有效：看图、看推导，还是动手实践？",
            "你通常通过什么方式最容易理解一个新概念？",
        ),
        "time_budget": (
            "你每周能学习几天、每天大约投入多少分钟？",
            "方便说说你一周的学习频率和每天可用的时间吗？",
            "为了控制学习节奏，你每周和每天大概能安排多少时间？",
        ),
    }
    _question_dimension_labels = {
        "major": "专业或主要学习方向",
        "knowledge_level": "当前基础程度",
        "learning_goals": "具体学习目标",
        "weak_topics": "最需要补强的知识点",
        "cognitive_style": "最适合你的学习方式",
        "time_budget": "每周和每天可安排的学习时间",
    }
    _question_target_patterns = (
        (
            "weak_topics",
            (
                r"薄弱|困惑|不懂|不会|难点|困难|卡住|没弄懂|不理解|最难|补强",
                r"哪些.*(?:概念|题型).*(?:困惑|不会|不熟)",
            ),
        ),
        ("time_budget", (r"每天|每周|一周|分钟|小时|学习时间|投入.*时间|安排.*时间",)),
        ("major", (r"专业|主修|学习方向|所在院系",)),
        ("learning_goals", (r"目标|达成|学完.*(?:能够|能)|成果|希望.*完成",)),
        (
            "cognitive_style",
            (r"学习方式|理解方式|图示理解|原理推导|边做边学|看图.*推导|动手实践",),
        ),
        (
            "knowledge_level",
            (r"掌握.*程度|目前.*程度|基础程度|已有基础|接触过|相关经验|学习起点",),
        ),
        ("course", (r"哪门课程|课程名称|具体.*课程|正在学什么",)),
        ("learning_history", (r"学习经历|学过什么|完成过",)),
        ("language_preference", (r"中文|英文|语言偏好",)),
        ("resource_preference", (r"资源偏好|材料偏好|视频|代码案例|阅读材料",)),
    )

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        enable_llm: bool = False,
        fallback: DevelopmentProfileAgent | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._enable_llm = enable_llm
        self._fallback = fallback or DevelopmentProfileAgent()

    async def extract(
        self,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> ProfileChatResponse:
        if not self._enable_llm:
            logger.warning("profile_fallback reason=llm_disabled")
            response = self._fallback.extract(request, previous)
            return self._stabilize_next_question(response, request, previous)
        if self._llm_client is None:
            logger.warning("profile_fallback reason=llm_client_unavailable")
            response = self._fallback.extract(request, previous)
            return self._stabilize_next_question(response, request, previous)
        try:
            draft = await self._generate_draft(request, previous)
            self._validate_evidence(draft, request)
            response = self._build_response(draft, request, previous)
            return self._stabilize_next_question(response, request, previous)
        except (LLMError, ValidationError, ValueError) as error:
            logger.warning(
                "profile_fallback reason=structured_extraction_failed error=%s",
                safe_error_summary(error),
            )
            response = self._fallback.extract(request, previous)
            return self._stabilize_next_question(response, request, previous)

    async def _generate_draft(
        self,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> ProfileExtractionDraft:
        prompt_payload = self._prompt_payload(request, previous)
        for attempt in range(2):
            system_prompt = PROFILE_SYSTEM_PROMPT
            if attempt:
                system_prompt += (
                    "\nFORMAT REPAIR: Regenerate the complete JSON object once. "
                    "Follow the schema exactly; do not add fields, commentary, "
                    "or Markdown. Preserve traceable evidence quotations."
                )
            try:
                draft = await self._llm_client.generate_structured(
                    system_prompt=system_prompt,
                    messages=[LLMMessage(role="user", content=prompt_payload)],
                    response_model=ProfileExtractionDraft,
                )
                if attempt:
                    logger.info("profile_format_repair success=true")
                return draft
            except (
                LLMResponseFormatError,
                LLMValidationError,
                ValidationError,
            ) as error:
                if attempt:
                    raise
                logger.warning(
                    "profile_format_repair requested=true error=%s",
                    safe_error_summary(error),
                )
        raise LLMValidationError("profile format repair exhausted")

    @classmethod
    def _stabilize_next_question(
        cls,
        response: ProfileChatResponse,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> ProfileChatResponse:
        missing = [
            dimension
            for dimension in response.missing_dimensions
            if dimension in cls._question_variants
        ]
        if not missing:
            response.next_question = None
            return response

        candidate = response.next_question or cls._question_variants[missing[0]][0]
        target = cls._question_dimension(candidate)
        if target not in missing:
            target = missing[0]
            candidate = cls._question_variants[target][0]

        unchanged = previous is not None and cls._business_values(
            response.profile
        ) == cls._business_values(previous)
        if not unchanged:
            response.next_question = candidate
            return response

        asked = [
            cls._normalize_question(message.content)
            for message in request.messages
            if message.role == "assistant"
        ]
        normalized_candidate = cls._normalize_question(candidate)
        if asked.count(normalized_candidate) < 2:
            response.next_question = candidate
            return response

        replacement = cls._replacement_question(target, missing, asked, normalized_candidate)
        response.next_question = replacement
        return response

    @classmethod
    def _replacement_question(
        cls,
        target: str,
        missing: list[str],
        asked: list[str],
        normalized_candidate: str,
    ) -> str:
        ordered_dimensions = [target, *(item for item in missing if item != target)]
        for dimension in ordered_dimensions:
            for variant in cls._question_variants[dimension]:
                normalized_variant = cls._normalize_question(variant)
                if (
                    normalized_variant != normalized_candidate
                    and asked.count(normalized_variant) < 2
                ):
                    return variant

        target_counts = {
            dimension: sum(
                cls._question_dimension(question) == dimension for question in asked
            )
            for dimension in ordered_dimensions
        }
        next_target = min(ordered_dimensions, key=target_counts.get)
        next_attempt = target_counts[next_target] + 1
        label = cls._question_dimension_labels[next_target]
        return (
            f"我还需要确认你的{label}。如果暂时不确定，可以先给出大致情况，"
            f"或直接回复“暂不确定”（第{next_attempt}次补充）。"
        )

    @staticmethod
    def _business_values(profile: StudentProfile) -> dict[str, object]:
        return {
            field_name: getattr(profile, field_name).model_dump(mode="json")["value"]
            for field_name in DevelopmentProfileAgent._profile_field_names()
        }

    @staticmethod
    def _normalize_question(question: str) -> str:
        return re.sub(r"\s+", "", question).strip()

    @classmethod
    def _question_dimension(cls, question: str) -> str | None:
        normalized = cls._normalize_question(question)
        for dimension, patterns in cls._question_target_patterns:
            if any(re.search(pattern, normalized) for pattern in patterns):
                return dimension
        return None

    @staticmethod
    def _prompt_payload(
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> str:
        payload = {
            "student_id": request.student_id,
            "conversation_id": request.conversation_id,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "previous_profile": (
                ProfileAgent._compact_previous_profile(previous) if previous else None
            ),
            "evaluation_summary": request.evaluation_summary,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_previous_profile(profile: StudentProfile) -> dict[str, object]:
        """Keep values and provenance types without repeating evidence quotations."""

        compact: dict[str, object] = {
            "student_id": profile.student_id,
            "version": profile.version,
            "confidence": profile.confidence,
        }
        for field_name in DevelopmentProfileAgent._profile_field_names():
            profile_field = getattr(profile, field_name)
            compact[field_name] = {
                "value": profile_field.value.model_dump(mode="json")
                if isinstance(profile_field.value, TimeBudget)
                else profile_field.value,
                "confidence": profile_field.confidence,
                "evidence_sources": sorted(
                    {evidence.source for evidence in profile_field.evidence}
                ),
            }
        return compact

    @staticmethod
    def _validate_evidence(
        draft: ProfileExtractionDraft,
        request: ProfileChatRequest,
    ) -> None:
        user_messages = {
            message.message_id: message.content
            for message in request.messages
            if message.role == "user"
        }
        for field_name in DevelopmentProfileAgent._profile_field_names():
            profile_field = getattr(draft, field_name)
            has_value = profile_field.value not in (None, [])
            issue: str | None = None
            if has_value and not profile_field.evidence:
                issue = "value_without_evidence"
            elif not has_value and (
                profile_field.evidence or profile_field.confidence != 0
            ):
                issue = "empty_value_with_evidence"
            for evidence in profile_field.evidence if issue is None else []:
                if evidence.source == "conversation":
                    content = user_messages.get(evidence.message_id or "")
                    if not content or evidence.quote not in content:
                        issue = "conversation_evidence_untraceable"
                elif evidence.source == "evaluation":
                    summary = request.evaluation_summary or ""
                    if evidence.message_id is not None or evidence.quote not in summary:
                        issue = "evaluation_evidence_untraceable"
                elif evidence.source == "inference":
                    if evidence.message_id is not None:
                        content = user_messages.get(evidence.message_id)
                        if not content or evidence.quote not in content:
                            issue = "inference_evidence_untraceable"
                    elif not evidence.quote.startswith("推断："):
                        issue = "inference_explanation_missing"
                elif evidence.source == "system_default":
                    if evidence.message_id is not None or "默认" not in evidence.quote:
                        issue = "system_default_evidence_invalid"
                if issue is not None:
                    break

            if issue is None:
                continue
            logger.warning(
                "profile_field_discarded field=%s reason=%s",
                field_name,
                issue,
            )
            profile_field.value = [] if isinstance(profile_field.value, list) else None
            profile_field.evidence = []
            profile_field.confidence = 0.0

    def _build_response(
        self,
        draft: ProfileExtractionDraft,
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> ProfileChatResponse:
        fields: dict[str, ProfileField] = {}
        for field_name in DevelopmentProfileAgent._profile_field_names():
            new_field = getattr(draft, field_name).model_copy(deep=True)
            old_field = getattr(previous, field_name) if previous else None
            fields[field_name] = self._merge_field(new_field, old_field)

        fields = self._supplement_explicit_fields(
            fields,
            request,
            previous,
        )

        if fields["course"].value is None:
            fields["course"] = ProfileField(
                value="机器学习基础",
                evidence=[
                    FieldEvidence(
                        source="system_default",
                        quote="默认演示课程：《机器学习基础》",
                    )
                ],
                confidence=0.55,
            )

        profile = StudentProfile(
            student_id=request.student_id,
            version=(previous.version + 1) if previous else 1,
            **fields,
            evidence=[],
            confidence=0.0,
            updated_at=utc_now(),
        )
        profile.evidence = DevelopmentProfileAgent._consolidated_evidence(profile, [])
        profile.confidence = DevelopmentProfileAgent._overall_confidence(profile)
        missing = self._fallback._missing_dimensions(profile)
        next_question = None
        if missing:
            next_question = draft.next_question or self._fallback._next_question(missing[0])
        return ProfileChatResponse(
            profile=profile,
            missing_dimensions=missing,
            next_question=next_question,
            is_complete=not missing,
            extraction_mode="llm_structured",
        )

    def _supplement_explicit_fields(
        self,
        fields: dict[str, ProfileField],
        request: ProfileChatRequest,
        previous: StudentProfile | None,
    ) -> dict[str, ProfileField]:
        supplemental = self._fallback.extract(request, previous).profile
        for field_name in DevelopmentProfileAgent._profile_field_names():
            current = fields[field_name]
            explicit = getattr(supplemental, field_name)
            if current.value in (None, []) and explicit.value not in (None, []):
                fields[field_name] = explicit.model_copy(deep=True)

        fields["weak_topics"] = self._merge_supplemental_list(
            fields["weak_topics"],
            supplemental.weak_topics,
        )
        fields["resource_preference"] = self._merge_supplemental_list(
            fields["resource_preference"],
            supplemental.resource_preference,
            category_key=self._resource_preference_category,
        )
        return fields

    def _merge_supplemental_list(
        self,
        current: ProfileField,
        supplemental: ProfileField,
        *,
        category_key: Callable[[str], str] | None = None,
    ) -> ProfileField:
        current_values = list(current.value) if isinstance(current.value, list) else []
        supplemental_values = (
            list(supplemental.value) if isinstance(supplemental.value, list) else []
        )
        key = category_key or (lambda value: value)
        known = {key(value) for value in current_values}
        new_values = [value for value in supplemental_values if key(value) not in known]
        if not new_values:
            return current

        merged = current.model_copy(deep=True)
        merged.value = [*current_values, *new_values]
        merged.evidence = self._fallback._deduplicate_evidence(
            [*merged.evidence, *supplemental.evidence]
        )
        merged.confidence = max(merged.confidence, supplemental.confidence)
        return merged

    @staticmethod
    def _resource_preference_category(value: str) -> str:
        categories = {
            "code": ("代码", "编程", "实践"),
            "visual": ("图", "可视化", "导图"),
            "exercise": ("练习", "做题", "题目"),
            "reading": ("阅读", "论文", "资料"),
            "explanation": ("文档", "讲解"),
        }
        for category, keywords in categories.items():
            if any(keyword in value for keyword in keywords):
                return category
        return value

    @staticmethod
    def _merge_field(
        new_field: ProfileField,
        old_field: ProfileField | None,
    ) -> ProfileField:
        if new_field.value in (None, []):
            return old_field.model_copy(deep=True) if old_field else new_field

        sources = {evidence.source for evidence in new_field.evidence}
        if sources == {"system_default"}:
            new_field.confidence = min(new_field.confidence, 0.55)
        elif "inference" in sources and not sources.intersection(
            {"conversation", "evaluation"}
        ):
            new_field.confidence = min(new_field.confidence, 0.74)

        if isinstance(new_field.value, list) and old_field and isinstance(old_field.value, list):
            new_field.value = list(dict.fromkeys([*old_field.value, *new_field.value]))
            new_field.evidence = DevelopmentProfileAgent._deduplicate_evidence(
                [*old_field.evidence, *new_field.evidence]
            )
        return new_field
