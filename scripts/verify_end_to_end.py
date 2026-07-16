from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
TERMINAL_TASK_STATUSES = {"completed", "partial_success", "failed"}
RESOURCE_TYPES = {"explanation", "mind_map", "quiz", "reading", "coding"}
ACCEPTANCE_TEXT = (
    "我是人工智能专业大二学生，目前在学习机器学习，"
    "数学基础一般，梯度下降一直没弄懂，希望完成一个分类项目。"
    "我每天可以学习45分钟，偏好代码案例和图示。"
)
INITIAL_ASSISTANT_MESSAGE = (
    "你好，我会通过对话了解你的学习情况。请告诉我你的专业、课程、目标、"
    "薄弱点、偏好和可用学习时间。"
)


class VerificationError(RuntimeError):
    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ConfigurationError(RuntimeError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__("invalid_configuration")
        self.missing = missing


@dataclass(slots=True)
class StageResult:
    name: str
    success: bool
    elapsed_ms: float


class StageRecorder:
    def __init__(self) -> None:
        self.results: list[StageResult] = []
        self.current: str | None = None

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        self.current = name
        try:
            yield
        except BaseException:
            self.results.append(
                StageResult(
                    name=name,
                    success=False,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            )
            raise
        else:
            self.results.append(
                StageResult(
                    name=name,
                    success=True,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            )
        finally:
            self.current = None

    @property
    def failed_stage(self) -> str | None:
        return next(
            (result.name for result in reversed(self.results) if not result.success),
            self.current,
        )


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_configuration() -> dict[str, object]:
    if not ENV_PATH.is_file():
        raise ConfigurationError([".env"])

    load_dotenv(dotenv_path=ENV_PATH, override=False)
    missing: list[str] = []
    if not _env_enabled("ENABLE_LLM"):
        missing.append("ENABLE_LLM=true")
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"):
        if not os.getenv(name, "").strip():
            missing.append(name)
    if missing:
        raise ConfigurationError(missing)

    return {
        "ENABLE_LLM": True,
        "provider": os.getenv("LLM_PROVIDER", "").strip().lower(),
        "model": os.getenv("LLM_MODEL", "").strip(),
        "api_key_present": bool(os.getenv("LLM_API_KEY", "").strip()),
    }


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationError(code)


def _synthetic_tag(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _profile_value(profile: dict[str, Any], name: str) -> Any:
    field = profile.get(name)
    return field.get("value") if isinstance(field, dict) else None


def _joined_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _extract_optional_new_path_id(evaluation: dict[str, Any]) -> str | None:
    candidates: list[Any] = [evaluation.get("new_path_id")]
    suggestions = evaluation.get("path_update_suggestions")
    if isinstance(suggestions, dict):
        candidates.extend(
            (
                suggestions.get("new_path_id"),
                suggestions.get("path_id"),
            )
        )
    for name in ("path", "updated_path", "new_path"):
        path_value = evaluation.get(name)
        if isinstance(path_value, dict):
            candidates.append(path_value.get("path_id"))
    return next(
        (candidate for candidate in candidates if isinstance(candidate, str) and candidate),
        None,
    )


def _extract_optional_updated_path(evaluation: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[Any] = [
        evaluation.get("path"),
        evaluation.get("updated_path"),
        evaluation.get("new_path"),
    ]
    suggestions = evaluation.get("path_update_suggestions")
    if isinstance(suggestions, dict):
        candidates.extend(
            (
                suggestions.get("path"),
                suggestions.get("updated_path"),
                suggestions.get("new_path"),
            )
        )
    return next((candidate for candidate in candidates if isinstance(candidate, dict)), None)


class EndToEndVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: float,
        task_timeout_seconds: float,
        poll_interval_seconds: float,
        allow_development_modes: bool,
        verify_cache: bool = False,
    ) -> None:
        timeout = httpx.Timeout(
            request_timeout_seconds,
            connect=min(request_timeout_seconds, 10.0),
            read=max(request_timeout_seconds, 20.0),
        )
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "EduAgent-E2E-Verifier/1.0",
            },
        )
        self.task_timeout_seconds = task_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.allow_development_modes = allow_development_modes
        self.verify_cache = verify_cache
        self.stages = StageRecorder()

    def close(self) -> None:
        self.client.close()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, json=payload)
        except httpx.TimeoutException as error:
            raise VerificationError("http_timeout") from error
        except httpx.HTTPError as error:
            raise VerificationError("http_transport_error") from error
        if response.status_code != expected_status:
            raise VerificationError(
                "unexpected_http_status",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except (TypeError, ValueError) as error:
            raise VerificationError("response_is_not_json") from error
        if not isinstance(body, dict):
            raise VerificationError("response_is_not_object")
        return body

    def _verify_profile(self, response: dict[str, Any]) -> dict[str, Any]:
        profile = response.get("profile")
        _require(isinstance(profile, dict), "profile_missing")
        assert isinstance(profile, dict)

        mode = response.get("extraction_mode")
        if not self.allow_development_modes:
            _require(mode == "llm_structured", "profile_not_llm_structured")
        else:
            _require(
                mode in {"llm_structured", "development_heuristic"},
                "profile_mode_invalid",
            )

        major = _joined_text(_profile_value(profile, "major"))
        course = _joined_text(_profile_value(profile, "course"))
        goals = _joined_text(_profile_value(profile, "learning_goals"))
        weak_topics = _joined_text(_profile_value(profile, "weak_topics"))
        knowledge_level = _profile_value(profile, "knowledge_level")
        preferences = " ".join(
            (
                _joined_text(_profile_value(profile, "resource_preference")),
                _joined_text(_profile_value(profile, "cognitive_style")),
            )
        ).lower()
        time_budget = _profile_value(profile, "time_budget")

        _require("人工智能" in major, "profile_major_incorrect")
        _require("机器学习" in course, "profile_course_incorrect")
        _require("分类" in goals and "项目" in goals, "profile_goal_incorrect")
        _require(
            knowledge_level in {"beginner", "intermediate"},
            "profile_knowledge_level_incorrect",
        )
        _require(
            "数学基础" in weak_topics and "梯度下降" in weak_topics,
            "profile_weak_topics_incorrect",
        )
        _require(
            any(token in preferences for token in ("代码", "coding", "code")),
            "profile_code_preference_missing",
        )
        _require(
            any(token in preferences for token in ("图", "visual", "diagram")),
            "profile_visual_preference_missing",
        )
        _require(
            isinstance(time_budget, dict)
            and time_budget.get("minutes_per_day") == 45,
            "profile_time_budget_incorrect",
        )

        next_question = response.get("next_question")
        _require(
            next_question is None or isinstance(next_question, str),
            "profile_next_question_invalid",
        )
        missing_dimensions = response.get("missing_dimensions")
        _require(isinstance(missing_dimensions, list), "profile_missing_dimensions_invalid")
        if not missing_dimensions:
            _require(next_question is None, "profile_reasks_identified_field")
        return profile

    def _verify_path(
        self,
        path: Any,
        *,
        student_id: str,
        profile_version: int,
    ) -> dict[str, Any]:
        _require(isinstance(path, dict), "path_missing")
        assert isinstance(path, dict)
        _require(path.get("student_id") == student_id, "path_student_mismatch")
        _require(path.get("profile_version") == profile_version, "path_profile_mismatch")
        mode = path.get("generation_mode")
        if not self.allow_development_modes:
            _require(mode == "llm_structured", "path_not_llm_structured")
        else:
            _require(
                mode in {"llm_structured", "development_rule_based"},
                "path_mode_invalid",
            )
        steps = path.get("steps")
        _require(isinstance(steps, list) and bool(steps), "path_steps_missing")
        assert isinstance(steps, list)
        _require(
            [step.get("step") for step in steps if isinstance(step, dict)]
            == list(range(1, len(steps) + 1)),
            "path_steps_not_contiguous",
        )
        required_fields = {
            "topic",
            "learning_goal",
            "reason",
            "recommended_resources",
            "completion_criteria",
            "estimated_minutes",
            "prerequisites",
        }
        for step in steps:
            _require(isinstance(step, dict), "path_step_invalid")
            assert isinstance(step, dict)
            _require(required_fields.issubset(step), "path_step_fields_missing")
            _require(bool(str(step.get("topic") or "").strip()), "path_step_topic_missing")
            _require(
                bool(str(step.get("learning_goal") or "").strip()),
                "path_step_goal_missing",
            )
            _require(bool(str(step.get("reason") or "").strip()), "path_step_reason_missing")
            _require(bool(step.get("recommended_resources")), "path_step_resources_missing")
            _require(bool(step.get("completion_criteria")), "path_step_criteria_missing")
            _require(
                isinstance(step.get("estimated_minutes"), int)
                and step["estimated_minutes"] > 0,
                "path_step_minutes_invalid",
            )
            _require(isinstance(step.get("prerequisites"), list), "path_step_prerequisites_invalid")

        topics = [str(step["topic"]).strip() for step in steps]
        _require(len(topics) == len(set(topics)), "path_steps_duplicated")
        priority_text = " ".join(topics[: min(2, len(topics))])
        _require(
            any(token in priority_text for token in ("数学", "线性代数", "微积分", "导数")),
            "path_does_not_prioritize_math",
        )
        _require("梯度下降" in priority_text, "path_does_not_prioritize_gradient_descent")
        project_text = " ".join(
            f"{step.get('topic', '')} {step.get('learning_goal', '')}" for step in steps
        )
        _require(
            "分类" in project_text and "项目" in project_text,
            "path_classification_project_missing",
        )
        return path

    def _consume_sse(self, events_url: str) -> dict[str, Any]:
        started = time.monotonic()
        last_sequence = 0
        event_count = 0
        event_type_counts: Counter[str] = Counter()
        retrieval_completed_types: set[str] = set()
        review_completed_types: set[str] = set()
        cache_hit_types: set[str] = set()
        terminal_event_seen = False
        try:
            with self.client.stream(
                "GET",
                events_url,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    raise VerificationError(
                        "sse_unexpected_http_status",
                        status_code=response.status_code,
                    )
                content_type = response.headers.get("content-type", "")
                _require(content_type.startswith("text/event-stream"), "sse_content_type_invalid")
                for line in response.iter_lines():
                    if time.monotonic() - started > self.task_timeout_seconds:
                        raise VerificationError("sse_task_timeout")
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    try:
                        event = json.loads(raw)
                    except (TypeError, ValueError) as error:
                        raise VerificationError("sse_event_invalid_json") from error
                    _require(isinstance(event, dict), "sse_event_not_object")
                    assert isinstance(event, dict)
                    sequence = event.get("sequence")
                    _require(isinstance(sequence, int), "sse_sequence_invalid")
                    _require(sequence > last_sequence, "sse_sequence_not_increasing")
                    last_sequence = sequence
                    event_count += 1
                    event_type = str(event.get("event_type", "unknown"))
                    event_type_counts[event_type] += 1
                    resource_type = event.get("resource_type")
                    if (
                        event_type == "agent"
                        and event.get("agent") == "retriever_agent"
                        and event.get("status") == "completed"
                        and isinstance(resource_type, str)
                    ):
                        retrieval_completed_types.add(resource_type)
                    if (
                        event_type == "review"
                        and event.get("status") == "completed"
                        and isinstance(resource_type, str)
                    ):
                        review_completed_types.add(resource_type)
                    if (
                        event_type == "agent"
                        and "cache_hit=true" in str(event.get("message", ""))
                        and isinstance(resource_type, str)
                    ):
                        cache_hit_types.add(resource_type)
                    if (
                        event_type == "task"
                        and event.get("status") in TERMINAL_TASK_STATUSES
                    ):
                        terminal_event_seen = True
        except httpx.TimeoutException as error:
            raise VerificationError("sse_read_timeout") from error
        except httpx.HTTPError as error:
            raise VerificationError("sse_transport_error") from error

        _require(event_count > 0, "sse_no_events")
        _require(event_type_counts["agent"] > 0, "sse_no_agent_events")
        _require(event_type_counts["review"] > 0, "sse_no_review_events")
        _require(terminal_event_seen, "sse_no_terminal_task_event")
        _require(
            retrieval_completed_types == RESOURCE_TYPES,
            "sse_retrieval_events_incomplete",
        )
        _require(review_completed_types == RESOURCE_TYPES, "sse_review_events_incomplete")
        return {
            "event_count": event_count,
            "last_sequence": last_sequence,
            "event_types": dict(sorted(event_type_counts.items())),
            "retrieval_completed_count": len(retrieval_completed_types),
            "review_completed_count": len(review_completed_types),
            "cache_hit_count": len(cache_hit_types),
            "cache_hit_types": sorted(cache_hit_types),
        }

    def _wait_for_task(self, status_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout_seconds
        while True:
            task = self._request_json("GET", status_url, expected_status=200)
            status = task.get("status")
            if status in TERMINAL_TASK_STATUSES:
                return task
            if time.monotonic() >= deadline:
                raise VerificationError("task_poll_timeout")
            time.sleep(self.poll_interval_seconds)

    @staticmethod
    def _answers_from_quiz(resource: dict[str, Any]) -> tuple[list[dict[str, str]], int]:
        content = resource.get("content")
        _require(isinstance(content, str), "quiz_content_missing")
        assert isinstance(content, str)
        try:
            document = json.loads(content)
        except (TypeError, ValueError) as error:
            raise VerificationError("quiz_content_invalid_json") from error
        _require(isinstance(document, dict), "quiz_document_not_object")
        questions = document.get("questions") if isinstance(document, dict) else None
        _require(isinstance(questions, list) and bool(questions), "quiz_questions_missing")
        assert isinstance(questions, list)

        deliberately_wrong = max(1, len(questions) - 1)
        answers: list[dict[str, str]] = []
        for index, question in enumerate(questions):
            _require(isinstance(question, dict), "quiz_question_invalid")
            assert isinstance(question, dict)
            question_id = question.get("id")
            correct_answer = question.get("answer")
            _require(isinstance(question_id, str) and bool(question_id), "quiz_question_id_missing")
            _require(
                isinstance(correct_answer, str) and bool(correct_answer.strip()),
                "quiz_answer_missing",
            )
            response = "本题故意答错"
            if index >= deliberately_wrong:
                response = correct_answer
            answers.append({"question_id": question_id, "response": response})
        return answers, deliberately_wrong

    @staticmethod
    def _evaluation_summary(evaluation: dict[str, Any]) -> str:
        feedback = evaluation.get("feedback")
        weak_topics = evaluation.get("weak_topics")
        safe_feedback = feedback if isinstance(feedback, str) else "评价要求更新学习安排。"
        safe_weak_topics = (
            "、".join(str(item) for item in weak_topics)
            if isinstance(weak_topics, list)
            else ""
        )
        return f"{safe_feedback[:3000]}\n薄弱知识点：{safe_weak_topics}"[:4000]

    def run(self) -> dict[str, Any]:
        student_id = f"e2e-{uuid4().hex}"
        conversation_id = f"conversation-{uuid4().hex}"
        messages: list[dict[str, str]] = [
            {
                "message_id": f"assistant-{uuid4().hex}",
                "role": "assistant",
                "content": INITIAL_ASSISTANT_MESSAGE,
            },
            {
                "message_id": f"user-{uuid4().hex}",
                "role": "user",
                "content": ACCEPTANCE_TEXT,
            },
        ]

        with self.stages.track("health"):
            health = self._request_json("GET", "/api/health", expected_status=200)
            _require(health.get("status") == "ok", "health_not_ok")
            _require(health.get("database") == "ok", "database_not_ok")

        with self.stages.track("profile"):
            profile_response = self._request_json(
                "POST",
                "/api/profile/chat",
                expected_status=200,
                payload={
                    "student_id": student_id,
                    "conversation_id": conversation_id,
                    "messages": messages,
                    "evaluation_summary": None,
                },
            )
            profile = self._verify_profile(profile_response)
            _require(profile.get("student_id") == student_id, "profile_student_mismatch")
            stored_profile = self._request_json(
                "GET",
                f"/api/profile/{student_id}",
                expected_status=200,
            )
            _require(
                stored_profile.get("version") == profile.get("version"),
                "profile_not_persisted",
            )

        assistant_reply = profile_response.get("next_question")
        if not isinstance(assistant_reply, str) or not assistant_reply:
            assistant_reply = "画像已更新，我会据此安排下一步学习路径。"
        messages.append(
            {
                "message_id": f"assistant-{uuid4().hex}",
                "role": "assistant",
                "content": assistant_reply,
            }
        )

        with self.stages.track("planner"):
            path_response = self._request_json(
                "POST",
                "/api/path/generate",
                expected_status=200,
                payload={
                    "student_id": student_id,
                    "profile": profile,
                    "previous_path_id": None,
                    "evaluation_summary": None,
                },
            )
            profile_version = profile.get("version")
            _require(isinstance(profile_version, int), "profile_version_invalid")
            path = self._verify_path(
                path_response.get("path"),
                student_id=student_id,
                profile_version=profile_version,
            )

        with self.stages.track("resource_generation_and_sse"):
            accepted = self._request_json(
                "POST",
                "/api/resources/generate",
                expected_status=202,
                payload={
                    "student_id": student_id,
                    "path_id": path.get("path_id"),
                    "step": path["steps"][0]["step"],
                    "resource_types": sorted(RESOURCE_TYPES),
                    "regenerate": False,
                },
            )
            status_url = accepted.get("status_url")
            events_url = accepted.get("events_url")
            _require(isinstance(status_url, str) and bool(status_url), "task_status_url_missing")
            _require(isinstance(events_url, str) and bool(events_url), "task_events_url_missing")
            sse_summary = self._consume_sse(events_url)
            _require(
                sse_summary["cache_hit_count"] == 0,
                "cold_resource_task_unexpected_cache_hit",
            )
            task = self._wait_for_task(status_url)
            _require(task.get("status") == "completed", "resource_task_not_completed")
            resource_ids = task.get("result_resource_ids")
            _require(
                isinstance(resource_ids, list) and len(resource_ids) == len(RESOURCE_TYPES),
                "five_resources_not_generated",
            )

        with self.stages.track("resource_validation"):
            resources: list[dict[str, Any]] = []
            for resource_id in resource_ids:
                _require(isinstance(resource_id, str), "resource_id_invalid")
                resources.append(
                    self._request_json(
                        "GET",
                        f"/api/resources/{resource_id}",
                        expected_status=200,
                    )
                )
            generated_types = {resource.get("resource_type") for resource in resources}
            _require(generated_types == RESOURCE_TYPES, "resource_types_incomplete")
            _require(
                all(
                    isinstance(resource.get("source_references"), list)
                    and bool(resource["source_references"])
                    for resource in resources
                ),
                "resource_source_missing",
            )
            _require(
                all(
                    resource.get("review_status") == "approved"
                    for resource in resources
                ),
                "resource_review_not_approved",
            )
            _require(
                all(
                    isinstance(resource.get("personalization_reason"), str)
                    and "梯度下降" in resource["personalization_reason"]
                    for resource in resources
                ),
                "resource_personalization_missing",
            )
            unique_source_chunks = {
                (reference.get("locator"), reference.get("chunk_id"))
                for resource in resources
                for reference in resource.get("source_references", [])
                if isinstance(reference, dict)
                and reference.get("locator")
                and reference.get("chunk_id") != "fallback"
            }
            _require(bool(unique_source_chunks), "rag_real_source_missing")
            quiz_resource = next(
                resource for resource in resources if resource.get("resource_type") == "quiz"
            )
            answers, deliberately_wrong = self._answers_from_quiz(quiz_resource)

        cache_summary: dict[str, Any] | None = None
        if self.verify_cache:
            with self.stages.track("warm_resource_cache"):
                warm_accepted = self._request_json(
                    "POST",
                    "/api/resources/generate",
                    expected_status=202,
                    payload={
                        "student_id": student_id,
                        "path_id": path.get("path_id"),
                        "step": path["steps"][0]["step"],
                        "resource_types": sorted(RESOURCE_TYPES),
                        "regenerate": False,
                    },
                )
                warm_status_url = warm_accepted.get("status_url")
                warm_events_url = warm_accepted.get("events_url")
                _require(
                    isinstance(warm_status_url, str) and bool(warm_status_url),
                    "warm_task_status_url_missing",
                )
                _require(
                    isinstance(warm_events_url, str) and bool(warm_events_url),
                    "warm_task_events_url_missing",
                )
                warm_sse = self._consume_sse(warm_events_url)
                warm_task = self._wait_for_task(warm_status_url)
                _require(
                    warm_task.get("status") == "completed",
                    "warm_resource_task_not_completed",
                )
                warm_resource_ids = warm_task.get("result_resource_ids")
                _require(
                    isinstance(warm_resource_ids, list)
                    and len(warm_resource_ids) == len(RESOURCE_TYPES),
                    "warm_five_resources_not_generated",
                )
                _require(
                    set(warm_resource_ids).isdisjoint(set(resource_ids)),
                    "warm_cache_reused_resource_ids",
                )
                _require(
                    warm_sse["cache_hit_count"] == len(RESOURCE_TYPES),
                    "warm_resource_cache_incomplete",
                )
                warm_resources = [
                    self._request_json(
                        "GET",
                        f"/api/resources/{resource_id}",
                        expected_status=200,
                    )
                    for resource_id in warm_resource_ids
                ]
                _require(
                    all(
                        resource.get("review_status") == "approved"
                        for resource in warm_resources
                    ),
                    "warm_resource_review_not_approved",
                )
                warm_quiz = next(
                    resource
                    for resource in warm_resources
                    if resource.get("resource_type") == "quiz"
                )
                warm_quiz_document = json.loads(str(warm_quiz.get("content", "")))
                warm_question_ids = {
                    str(question.get("id"))
                    for question in warm_quiz_document.get("questions", [])
                    if isinstance(question, dict)
                }
                cold_question_ids = {
                    str(question.get("id"))
                    for question in json.loads(str(quiz_resource.get("content", ""))).get(
                        "questions",
                        [],
                    )
                    if isinstance(question, dict)
                }
                _require(
                    bool(warm_question_ids)
                    and warm_question_ids.isdisjoint(cold_question_ids),
                    "warm_cache_reused_quiz_question_ids",
                )
                cache_summary = {
                    "verified": True,
                    "hit_count": warm_sse["cache_hit_count"],
                    "resource_ids_rebound": True,
                    "quiz_question_ids_rebound": True,
                    "reviewer_pass_count": sum(
                        resource.get("review_status") == "approved"
                        for resource in warm_resources
                    ),
                    "task_status": warm_task.get("status"),
                    "sse_event_count": warm_sse["event_count"],
                }

        with self.stages.track("evaluation"):
            evaluation = self._request_json(
                "POST",
                "/api/evaluation/submit",
                expected_status=200,
                payload={
                    "student_id": student_id,
                    "path_id": path.get("path_id"),
                    "step": path["steps"][0]["step"],
                    "answers": answers,
                    "time_spent_minutes": max(1, len(answers) * 2),
                },
            )
            _require(isinstance(evaluation.get("mastery_score"), (int, float)), "evaluation_score_missing")
            _require(isinstance(evaluation.get("passed"), bool), "evaluation_passed_missing")
            _require(evaluation.get("passed") is False, "evaluation_wrong_answers_not_detected")
            _require(bool(evaluation.get("weak_topics")), "evaluation_weak_topics_missing")
            update_requested = bool(evaluation.get("profile_update_required")) or bool(
                evaluation.get("path_update_required")
            )
            _require(update_requested, "evaluation_did_not_request_update")
            evaluation_summary = self._evaluation_summary(evaluation)
            evaluation_new_path_id = _extract_optional_new_path_id(evaluation)
            evaluation_updated_path = _extract_optional_updated_path(evaluation)
            profile_suggestions = evaluation.get("profile_update_suggestions")
            profile_suggestions = (
                profile_suggestions if isinstance(profile_suggestions, dict) else {}
            )

        with self.stages.track("profile_update"):
            queried_profile = self._request_json(
                "GET",
                f"/api/profile/{student_id}",
                expected_status=200,
            )
            if (
                isinstance(queried_profile.get("version"), int)
                and queried_profile["version"] > profile_version
            ):
                updated_profile = queried_profile
                profile_update_strategy = "evaluation_persisted"
                hinted_version = profile_suggestions.get("updated_profile_version")
                if isinstance(hinted_version, int):
                    _require(
                        updated_profile.get("version") == hinted_version,
                        "evaluation_profile_version_mismatch",
                    )
                hinted_mode = profile_suggestions.get("extraction_mode")
                if not self.allow_development_modes and isinstance(hinted_mode, str):
                    _require(
                        hinted_mode == "llm_structured",
                        "updated_profile_not_llm_structured",
                    )
            else:
                updated_profile_response = self._request_json(
                    "POST",
                    "/api/profile/chat",
                    expected_status=200,
                    payload={
                        "student_id": student_id,
                        "conversation_id": conversation_id,
                        "messages": messages,
                        "evaluation_summary": evaluation_summary,
                    },
                )
                updated_profile = self._verify_profile(updated_profile_response)
                profile_update_strategy = "evaluation_summary_roundtrip"
            _require(
                isinstance(updated_profile.get("version"), int)
                and updated_profile["version"] == profile_version + 1,
                "profile_version_not_updated",
            )
            weak_topic_field = updated_profile.get("weak_topics")
            weak_topic_evidence = (
                weak_topic_field.get("evidence", [])
                if isinstance(weak_topic_field, dict)
                else []
            )
            _require(
                any(
                    isinstance(evidence, dict) and evidence.get("source") == "evaluation"
                    for evidence in weak_topic_evidence
                ),
                "profile_evaluation_evidence_missing",
            )
            queried_profile = self._request_json(
                "GET",
                f"/api/profile/{student_id}",
                expected_status=200,
            )
            _require(
                queried_profile.get("version") == updated_profile.get("version"),
                "updated_profile_not_persisted",
            )

        with self.stages.track("path_update"):
            if evaluation_updated_path is not None:
                updated_path = self._verify_path(
                    evaluation_updated_path,
                    student_id=student_id,
                    profile_version=updated_profile["version"],
                )
                path_update_strategy = "evaluation_response_summary"
            else:
                updated_path_response = self._request_json(
                    "POST",
                    "/api/path/generate",
                    expected_status=200,
                    payload={
                        "student_id": student_id,
                        "profile": updated_profile,
                        "previous_path_id": path.get("path_id"),
                        "evaluation_summary": evaluation_summary,
                    },
                )
                updated_path = self._verify_path(
                    updated_path_response.get("path"),
                    student_id=student_id,
                    profile_version=updated_profile["version"],
                )
                path_update_strategy = "path_generate_roundtrip"
            _require(updated_path.get("path_id") != path.get("path_id"), "path_id_not_updated")
            _require(bool(updated_path.get("adjustment_reason")), "path_adjustment_reason_missing")
            if evaluation_new_path_id is not None and evaluation_updated_path is not None:
                _require(
                    updated_path.get("path_id") == evaluation_new_path_id,
                    "evaluation_new_path_id_mismatch",
                )

        review_counts = Counter(str(resource.get("review_status")) for resource in resources)
        return {
            "success": True,
            "student_tag": _synthetic_tag(student_id),
            "profile": {
                "extraction_mode": profile_response.get("extraction_mode"),
                "initial_version": profile_version,
                "updated_version": updated_profile.get("version"),
                "update_strategy": profile_update_strategy,
                "missing_dimensions_count": len(profile_response.get("missing_dimensions") or []),
                "next_question_present": bool(profile_response.get("next_question")),
            },
            "path": {
                "initial_generation_mode": path.get("generation_mode"),
                "updated_generation_mode": updated_path.get("generation_mode"),
                "initial_step_count": len(path.get("steps") or []),
                "updated_step_count": len(updated_path.get("steps") or []),
                "evaluation_new_path_id_present": evaluation_new_path_id is not None,
                "adjustment_reason_present": bool(updated_path.get("adjustment_reason")),
                "update_strategy": path_update_strategy,
            },
            "resources": {
                "task_status": task.get("status"),
                "types": sorted(generated_types),
                "success_count": len(resources),
                "source_coverage_count": sum(
                    1 for resource in resources if resource.get("source_references")
                ),
                "rag_hit_document_count": len(unique_source_chunks),
                "reviewer_pass_count": review_counts.get("approved", 0),
                "status_by_type": {
                    str(resource.get("resource_type")): str(resource.get("review_status"))
                    for resource in sorted(
                        resources,
                        key=lambda item: str(item.get("resource_type")),
                    )
                },
                "review_status_counts": dict(sorted(review_counts.items())),
                "sse": sse_summary,
            },
            "evaluation": {
                "mastery_score": evaluation.get("mastery_score"),
                "passed": evaluation.get("passed"),
                "deliberately_wrong_answer_count": deliberately_wrong,
                "profile_update_required": bool(evaluation.get("profile_update_required")),
                "path_update_required": bool(evaluation.get("path_update_required")),
                "evidence_source": profile_suggestions.get("evidence_source"),
                "profile_suggestions_present": isinstance(
                    evaluation.get("profile_update_suggestions"), dict
                ),
                "path_suggestions_present": isinstance(
                    evaluation.get("path_update_suggestions"), dict
                ),
            },
            "cache": cache_summary or {"verified": False},
            "stages": [asdict(stage) for stage in self.stages.results],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify EduAgent's HTTP profile, planner, five-resource, SSE, evaluation, "
            "and update flow without printing secrets or full responses."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--request-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--task-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--allow-development-modes",
        action="store_true",
        help="Allow explicit development fallbacks instead of requiring llm_structured.",
    )
    parser.add_argument(
        "--verify-cache",
        action="store_true",
        help="Repeat the five-resource task and require five safe cache hits.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.request_timeout_seconds <= 0 or args.task_timeout_seconds <= 0:
        print(json.dumps({"success": False, "error_category": "invalid_timeout"}))
        return 2
    if args.poll_interval_seconds <= 0:
        print(json.dumps({"success": False, "error_category": "invalid_poll_interval"}))
        return 2

    try:
        configuration = _load_configuration()
    except ConfigurationError as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "error_category": "invalid_configuration",
                    "missing": error.missing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    verifier = EndToEndVerifier(
        base_url=args.base_url,
        request_timeout_seconds=args.request_timeout_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        allow_development_modes=args.allow_development_modes,
        verify_cache=args.verify_cache,
    )
    try:
        summary = verifier.run()
        summary["configuration"] = configuration
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except VerificationError as error:
        failure: dict[str, object] = {
            "success": False,
            "configuration": configuration,
            "failed_stage": verifier.stages.failed_stage,
            "error_category": error.code,
            "stages": [asdict(stage) for stage in verifier.stages.results],
        }
        if error.status_code is not None:
            failure["http_status"] = error.status_code
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"success": False, "error_category": "interrupted"}))
        return 130
    except Exception as error:  # final privacy boundary: never print response or traceback
        print(
            json.dumps(
                {
                    "success": False,
                    "configuration": configuration,
                    "failed_stage": verifier.stages.failed_stage,
                    "error_category": f"unexpected_{type(error).__name__}",
                    "stages": [asdict(stage) for stage in verifier.stages.results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        verifier.close()


if __name__ == "__main__":
    raise SystemExit(main())
