from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel


_OPTION_PREFIX = re.compile(
    r"^\s*([A-Da-d])(?:[.\u3001:：)\]]|\s)+\s*(.+?)\s*$",
    re.DOTALL,
)
_ANSWER_LABEL = re.compile(r"^\s*([A-Da-d])(?:[.\u3001:：)\]]|\s|$)")
_ANSWER_PREFIX = re.compile(
    r"^\s*(?:答案|正确答案|选项)?\s*[:：]?\s*([A-Da-d])"
    r"(?:[.\u3001:：)\]]|\s|$)\s*(.*?)\s*$",
    re.DOTALL,
)
_QUESTION_METADATA = {"id", "type", "level"}


class QuizChoiceDraft(ApiModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=4, max_length=4)
    answer: str = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def discard_fixed_local_metadata(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: item
            for key, item in value.items()
            if key not in _QUESTION_METADATA
        }

    @field_validator("question", "explanation")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("quiz text must not be blank")
        return stripped

    @field_validator("options", mode="before")
    @classmethod
    def normalize_option_labels(cls, value: Any) -> Any:
        if not isinstance(value, list) or len(value) != 4:
            return value

        normalized: list[str] = []
        for index, raw_option in enumerate(value):
            expected_label = chr(ord("A") + index)
            if isinstance(raw_option, dict):
                label = str(raw_option.get("label") or "").strip().upper()
                text = str(
                    raw_option.get("text")
                    or raw_option.get("content")
                    or raw_option.get("option")
                    or ""
                ).strip()
                if label != expected_label or not text:
                    return value
                normalized.append(f"{expected_label}. {text}")
                continue
            if not isinstance(raw_option, str):
                return value
            option = raw_option.strip()
            matched = _OPTION_PREFIX.fullmatch(option)
            if matched:
                if matched.group(1).upper() != expected_label:
                    raise ValueError("quiz option labels must remain in A-D order")
                option = matched.group(2).strip()
            if not option:
                raise ValueError("quiz options must not be blank")
            normalized.append(f"{expected_label}. {option}")
        return normalized

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_answer_label(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        matched = _ANSWER_LABEL.match(stripped)
        if not matched:
            return stripped
        trailing = stripped[matched.end() :].strip()
        return matched.group(1).upper() if not trailing else stripped

    @model_validator(mode="after")
    def answer_must_match_one_option(self) -> "QuizChoiceDraft":
        raw_answer = self.answer.strip()
        if raw_answer in {"A", "B", "C", "D"}:
            return self

        option_bodies = [
            _OPTION_PREFIX.fullmatch(option).group(2).strip()
            for option in self.options
            if _OPTION_PREFIX.fullmatch(option)
        ]
        if len(option_bodies) != 4:
            raise ValueError("quiz options must have A-D labels")

        prefixed = _ANSWER_PREFIX.fullmatch(raw_answer)
        if prefixed:
            label = prefixed.group(1).upper()
            trailing = prefixed.group(2).strip()
            if not trailing:
                self.answer = label
                return self
            option_index = ord(label) - ord("A")
            if self._same_option_text(trailing, option_bodies[option_index]):
                self.answer = label
                return self

        matches = [
            index
            for index, option in enumerate(option_bodies)
            if self._same_option_text(raw_answer, option)
        ]
        if len(matches) == 1:
            self.answer = chr(ord("A") + matches[0])
            return self
        raise ValueError("quiz choice answer must identify exactly one option")

    @staticmethod
    def _same_option_text(left: str, right: str) -> bool:
        normalize = lambda value: re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()
        return bool(normalize(left)) and normalize(left) == normalize(right)


class QuizWrittenDraft(ApiModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def discard_fixed_local_metadata(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: item
            for key, item in value.items()
            if key not in {*_QUESTION_METADATA, "options"}
        }

    @field_validator("question", "answer", "explanation")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("quiz text must not be blank")
        return stripped


class QuizDraft(ApiModel):
    basic: QuizChoiceDraft
    intermediate: QuizWrittenDraft
    challenge: QuizWrittenDraft

    @model_validator(mode="before")
    @classmethod
    def normalize_exact_three_question_layout(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = {
            key: item
            for key, item in value.items()
            if key not in {"topic", "difficulty", "title"}
        }
        if {"basic", "intermediate", "challenge"} <= set(normalized):
            return normalized

        questions = normalized.get("questions")
        if (
            set(normalized) != {"questions"}
            or not isinstance(questions, list)
            or len(questions) != 3
        ):
            return normalized
        expected_levels = (
            {"", "basic", "基础"},
            {"", "intermediate", "进阶"},
            {"", "challenge", "advanced", "挑战", "综合"},
        )
        expected_types = (
            {"", "single_choice", "single-choice", "choice", "单选"},
            {"", "short_answer", "short-answer", "简答"},
            {"", "comprehensive", "综合"},
        )
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                return normalized
            level = str(question.get("level") or "").strip().casefold()
            question_type = str(question.get("type") or "").strip().casefold()
            if level not in expected_levels[index] or question_type not in expected_types[index]:
                return normalized
        return {
            "basic": questions[0],
            "intermediate": questions[1],
            "challenge": questions[2],
        }


class MindMapDraft(ApiModel):
    content: str = Field(min_length=1)


class ReadingDraft(ApiModel):
    overview: str = Field(min_length=1)
    core_points: list[str] = Field(min_length=3, max_length=3)
    practice_connection: str = Field(min_length=1)
    further_study: str = Field(min_length=1)

    @field_validator("overview", "practice_connection", "further_study")
    @classmethod
    def strip_required_paragraph(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reading paragraphs must not be blank")
        return stripped

    @field_validator("core_points")
    @classmethod
    def strip_core_points(cls, value: list[str]) -> list[str]:
        normalized = [point.strip() for point in value]
        if any(not point for point in normalized):
            raise ValueError("reading core points must not be blank")
        return normalized
