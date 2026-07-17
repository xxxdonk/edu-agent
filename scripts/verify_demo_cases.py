from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).with_name("demo_cases.json")
RESOURCE_TYPES = {"explanation", "mind_map", "quiz", "reading", "coding"}
TERMINAL_STATUSES = {"completed", "partial_success", "failed"}


class DemoVerificationError(RuntimeError):
    def __init__(self, code: str, *, case_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.case_id = case_id


def _require(condition: bool, code: str, case_id: str) -> None:
    if not condition:
        raise DemoVerificationError(code, case_id=case_id)


def _profile_value(profile: dict[str, Any], field: str) -> Any:
    value = profile.get(field)
    return value.get("value") if isinstance(value, dict) else None


def _joined(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values())
    return "" if value is None else str(value)


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = text.casefold()
    return any(str(token).casefold() in lowered for token in tokens)


def _safe_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def _load_cases() -> list[dict[str, Any]]:
    document = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list) or len(cases) != 3:
        raise DemoVerificationError("demo_cases_must_contain_exactly_three_cases")
    return cases


def _load_safe_configuration() -> dict[str, object]:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    enabled = os.getenv("ENABLE_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    key_present = bool(os.getenv("LLM_API_KEY", "").strip())
    if not enabled or not provider or not model or not key_present:
        raise DemoVerificationError("real_llm_configuration_missing")
    return {
        "ENABLE_LLM": True,
        "provider": provider,
        "model": model,
        "api_key_present": key_present,
    }


class DemoCaseVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: float,
        task_timeout_seconds: float,
        poll_interval_seconds: float,
        max_case_attempts: int,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(
                request_timeout_seconds,
                connect=min(10.0, request_timeout_seconds),
                read=max(20.0, request_timeout_seconds),
            ),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "EduAgent-Demo-Case-Verifier/1.0",
            },
        )
        self.task_timeout_seconds = task_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_case_attempts = max_case_attempts

    def close(self) -> None:
        self.client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        case_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, json=payload)
        except httpx.TimeoutException as error:
            raise DemoVerificationError("http_timeout", case_id=case_id) from error
        except httpx.HTTPError as error:
            raise DemoVerificationError("http_transport_error", case_id=case_id) from error
        if response.status_code != expected_status:
            raise DemoVerificationError(
                f"unexpected_http_status_{response.status_code}",
                case_id=case_id,
            )
        try:
            body = response.json()
        except ValueError as error:
            raise DemoVerificationError("response_not_json", case_id=case_id) from error
        _require(isinstance(body, dict), "response_not_object", case_id)
        return body

    def _wait_task(self, status_url: str, case_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout_seconds
        while time.monotonic() < deadline:
            task = self._request(
                "GET",
                status_url,
                expected_status=200,
                case_id=case_id,
            )
            if task.get("status") in TERMINAL_STATUSES:
                return task
            time.sleep(self.poll_interval_seconds)
        raise DemoVerificationError("resource_task_timeout", case_id=case_id)

    @staticmethod
    def _validate_profile(
        response: dict[str, Any],
        expected: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]:
        _require(
            response.get("extraction_mode") == "llm_structured",
            "profile_not_llm_structured",
            case_id,
        )
        profile = response.get("profile")
        _require(isinstance(profile, dict), "profile_missing", case_id)
        assert isinstance(profile, dict)

        major = _joined(_profile_value(profile, "major"))
        course = _joined(_profile_value(profile, "course"))
        level = _profile_value(profile, "knowledge_level")
        goals = _joined(_profile_value(profile, "learning_goals"))
        weak_topics = _joined(_profile_value(profile, "weak_topics"))
        preferences = " ".join(
            (
                _joined(_profile_value(profile, "resource_preference")),
                _joined(_profile_value(profile, "cognitive_style")),
            )
        )
        budget = _profile_value(profile, "time_budget")

        _require(_contains_any(major, expected["major_any"]), "major_mismatch", case_id)
        _require(_contains_any(course, expected["course_any"]), "course_mismatch", case_id)
        _require(level in expected["knowledge_level"], "knowledge_level_mismatch", case_id)
        _require(_contains_any(goals, expected["goal_any"]), "goal_mismatch", case_id)
        for group in expected["weak_topic_groups"]:
            _require(
                _contains_any(weak_topics, group),
                "weak_topic_group_missing",
                case_id,
            )
        _require(
            _contains_any(preferences, expected["preference_any"]),
            "resource_preference_mismatch",
            case_id,
        )
        _require(
            isinstance(budget, dict)
            and budget.get("minutes_per_day") == expected["time_budget_minutes"],
            "time_budget_mismatch",
            case_id,
        )
        return profile

    @staticmethod
    def _validate_path(
        response: dict[str, Any],
        expected: dict[str, Any],
        student_id: str,
        profile_version: int,
        case_id: str,
    ) -> dict[str, Any]:
        path = response.get("path")
        _require(isinstance(path, dict), "path_missing", case_id)
        assert isinstance(path, dict)
        _require(path.get("student_id") == student_id, "path_student_mismatch", case_id)
        _require(
            path.get("profile_version") == profile_version,
            "path_profile_version_mismatch",
            case_id,
        )
        _require(
            path.get("generation_mode") == "llm_structured",
            "path_not_llm_structured",
            case_id,
        )
        steps = path.get("steps")
        _require(isinstance(steps, list) and bool(steps), "path_steps_missing", case_id)
        assert isinstance(steps, list)
        topics = [str(step.get("topic", "")).strip() for step in steps if isinstance(step, dict)]
        _require(len(topics) == len(steps), "path_step_invalid", case_id)
        _require(len(topics) == len(set(topics)), "path_topics_duplicated", case_id)
        _require(
            [step.get("step") for step in steps]
            == list(range(1, len(steps) + 1)),
            "path_steps_not_contiguous",
            case_id,
        )
        priority_text = " ".join(
            " ".join(
                (
                    str(step.get("topic", "")),
                    str(step.get("learning_goal", "")),
                    str(step.get("reason", "")),
                )
            )
            for step in steps[: min(3, len(steps))]
        )
        full_text = " ".join(
            " ".join(
                (
                    str(step.get("topic", "")),
                    str(step.get("learning_goal", "")),
                    str(step.get("reason", "")),
                )
            )
            for step in steps
        )
        _require(
            _contains_any(priority_text, expected["priority_any"]),
            "path_priority_mismatch",
            case_id,
        )
        _require(
            _contains_any(full_text, expected["eventual_any"]),
            "path_goal_mismatch",
            case_id,
        )
        return path

    @staticmethod
    def _quiz_answers(
        quiz: dict[str, Any],
        strategy: str,
        case_id: str,
    ) -> list[dict[str, str]]:
        try:
            document = json.loads(str(quiz.get("content", "")))
        except ValueError as error:
            raise DemoVerificationError("quiz_json_invalid", case_id=case_id) from error
        questions = document.get("questions") if isinstance(document, dict) else None
        _require(isinstance(questions, list) and bool(questions), "quiz_empty", case_id)
        assert isinstance(questions, list)
        answers: list[dict[str, str]] = []
        wrong_count = 0
        for index, question in enumerate(questions):
            _require(isinstance(question, dict), "quiz_question_invalid", case_id)
            assert isinstance(question, dict)
            question_id = question.get("id")
            correct = question.get("answer")
            _require(isinstance(question_id, str), "quiz_question_id_missing", case_id)
            _require(isinstance(correct, str), "quiz_answer_key_missing", case_id)
            use_correct = (
                strategy == "alternating" and index % 2 == 0
            ) or (
                strategy == "first_correct" and index == 0
            )
            response = correct if use_correct else "与本题无关的错误答案"
            wrong_count += 0 if use_correct else 1
            answers.append({"question_id": question_id, "response": response})
        _require(wrong_count > 0, "quiz_strategy_has_no_wrong_answer", case_id)
        return answers

    def run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        case_id = str(case["id"])
        student_id = f"demo-{case_id}-{uuid4().hex}"
        started = time.perf_counter()

        profile_response = self._request(
            "POST",
            "/api/profile/chat",
            expected_status=200,
            case_id=case_id,
            payload={
                "student_id": student_id,
                "conversation_id": f"conversation-{uuid4().hex}",
                "messages": [
                    {
                        "message_id": f"message-{uuid4().hex}",
                        "role": "user",
                        "content": case["input"],
                    }
                ],
                "evaluation_summary": None,
            },
        )
        profile = self._validate_profile(
            profile_response,
            case["expected_profile"],
            case_id,
        )
        profile_version = profile.get("version")
        _require(isinstance(profile_version, int), "profile_version_invalid", case_id)

        path_response = self._request(
            "POST",
            "/api/path/generate",
            expected_status=200,
            case_id=case_id,
            payload={
                "student_id": student_id,
                "profile": profile,
                "previous_path_id": None,
                "evaluation_summary": None,
            },
        )
        path = self._validate_path(
            path_response,
            case["expected_path"],
            student_id,
            profile_version,
            case_id,
        )
        first_step = path["steps"][0]["step"]

        accepted = self._request(
            "POST",
            "/api/resources/generate",
            expected_status=202,
            case_id=case_id,
            payload={
                "student_id": student_id,
                "path_id": path["path_id"],
                "step": first_step,
                "resource_types": sorted(RESOURCE_TYPES),
                "regenerate": True,
            },
        )
        task = self._wait_task(str(accepted["status_url"]), case_id)
        _require(task.get("status") == "completed", "resource_task_not_completed", case_id)
        resource_ids = task.get("result_resource_ids")
        _require(
            isinstance(resource_ids, list) and len(resource_ids) == len(RESOURCE_TYPES),
            "five_resources_missing",
            case_id,
        )
        assert isinstance(resource_ids, list)

        resources = [
            self._request(
                "GET",
                f"/api/resources/{resource_id}",
                expected_status=200,
                case_id=case_id,
            )
            for resource_id in resource_ids
        ]
        _require(
            {resource.get("resource_type") for resource in resources} == RESOURCE_TYPES,
            "resource_types_mismatch",
            case_id,
        )
        _require(
            all(resource.get("review_status") == "approved" for resource in resources),
            "resource_review_failed",
            case_id,
        )
        _require(
            all(resource.get("source_references") for resource in resources),
            "resource_source_missing",
            case_id,
        )
        quiz = next(resource for resource in resources if resource["resource_type"] == "quiz")
        answers = self._quiz_answers(
            quiz,
            str(case["quiz_submission"]["strategy"]),
            case_id,
        )

        evaluation = self._request(
            "POST",
            "/api/evaluation/submit",
            expected_status=200,
            case_id=case_id,
            payload={
                "student_id": student_id,
                "path_id": path["path_id"],
                "step": first_step,
                "answers": answers,
                "time_spent_minutes": case["quiz_submission"]["time_spent_minutes"],
            },
        )
        _require(
            isinstance(evaluation.get("mastery_score"), (int, float)),
            "evaluation_score_missing",
            case_id,
        )
        updated_profile = self._request(
            "GET",
            f"/api/profile/{student_id}",
            expected_status=200,
            case_id=case_id,
        )
        _require(
            updated_profile.get("version") == profile_version + 1,
            "profile_version_not_incremented",
            case_id,
        )
        evidence = (
            updated_profile.get("weak_topics", {}).get("evidence", [])
            if isinstance(updated_profile.get("weak_topics"), dict)
            else []
        )
        _require(
            any(
                isinstance(item, dict) and item.get("source") == "evaluation"
                for item in evidence
            ),
            "evaluation_evidence_missing",
            case_id,
        )
        path_suggestions = evaluation.get("path_update_suggestions")
        _require(isinstance(path_suggestions, dict), "path_suggestions_missing", case_id)
        assert isinstance(path_suggestions, dict)
        updated_path = path_suggestions.get("updated_path")
        _require(isinstance(updated_path, dict), "updated_path_missing", case_id)
        assert isinstance(updated_path, dict)
        _require(
            updated_path.get("generation_mode") == "llm_structured",
            "updated_path_not_llm_structured",
            case_id,
        )
        _require(
            bool(updated_path.get("adjustment_reason")),
            "adjustment_reason_missing",
            case_id,
        )

        profile_signature = {
            "major": _profile_value(profile, "major"),
            "knowledge_level": _profile_value(profile, "knowledge_level"),
            "goals": _profile_value(profile, "learning_goals"),
            "weak_topics": _profile_value(profile, "weak_topics"),
            "preferences": _profile_value(profile, "resource_preference"),
            "time_budget": _profile_value(profile, "time_budget"),
        }
        resource_signature = [
            {
                "type": resource.get("resource_type"),
                "target": resource.get("target_topic"),
                "title": resource.get("title"),
                "personalization_reason": resource.get("personalization_reason"),
            }
            for resource in sorted(
                resources,
                key=lambda item: str(item.get("resource_type")),
            )
        ]
        fallback_types = sorted(
            str(resource["resource_type"])
            for resource in resources
            if "development fallback" in str(resource.get("personalization_reason", ""))
        )
        return {
            "case_id": case_id,
            "profile_mode": profile_response.get("extraction_mode"),
            "planner_mode": path.get("generation_mode"),
            "knowledge_level": _profile_value(profile, "knowledge_level"),
            "profile_signature": _safe_hash(profile_signature),
            "path_topics": [step["topic"] for step in path["steps"]],
            "path_signature": _safe_hash([step["topic"] for step in path["steps"]]),
            "resource_signature": _safe_hash(resource_signature),
            "resource_count": len(resources),
            "reviewer_approved_count": sum(
                resource.get("review_status") == "approved" for resource in resources
            ),
            "fallback_types": fallback_types,
            "evaluation_score": evaluation.get("mastery_score"),
            "profile_version_change": [profile_version, updated_profile.get("version")],
            "path_replanned": updated_path.get("path_id") != path.get("path_id"),
            "adjustment_reason_present": bool(updated_path.get("adjustment_reason")),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def run(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        health = self._request(
            "GET",
            "/api/health",
            expected_status=200,
            case_id="health",
        )
        _require(health.get("status") == "ok", "health_not_ok", "health")
        results: list[dict[str, Any]] = []
        for case in cases:
            prior_failures: list[str] = []
            for attempt in range(1, self.max_case_attempts + 1):
                try:
                    result = self.run_case(case)
                    result["attempt_count"] = attempt
                    result["prior_failure_codes"] = prior_failures
                    results.append(result)
                    break
                except DemoVerificationError as error:
                    prior_failures.append(error.code)
                    if attempt >= self.max_case_attempts:
                        raise

        for field in ("profile_signature", "path_signature", "resource_signature"):
            values = {str(result[field]) for result in results}
            _require(
                len(values) == len(results),
                f"cases_not_distinct_by_{field}",
                "cross_case",
            )
        return {
            "success": True,
            "case_count": len(results),
            "profiles_distinct": True,
            "paths_distinct": True,
            "resources_distinct": True,
            "cases": results,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run three synthetic EduAgent demo personas through profile, path, "
            "five resources, Quiz evaluation, and replanning."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--request-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--task-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--max-case-attempts",
        type=int,
        default=4,
        help=(
            "Maximum transparent attempts per synthetic case. Each attempt uses "
            "a fresh student_id and prior failure codes are reported."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        args.request_timeout_seconds <= 0
        or args.task_timeout_seconds <= 0
        or args.poll_interval_seconds <= 0
        or args.max_case_attempts <= 0
    ):
        print(json.dumps({"success": False, "error_category": "invalid_timeout"}))
        return 2

    try:
        configuration = _load_safe_configuration()
        cases = _load_cases()
    except DemoVerificationError as error:
        print(
            json.dumps(
                {"success": False, "error_category": error.code},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    verifier = DemoCaseVerifier(
        base_url=args.base_url,
        request_timeout_seconds=args.request_timeout_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        max_case_attempts=args.max_case_attempts,
    )
    try:
        summary = verifier.run(cases)
        summary["configuration"] = configuration
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except DemoVerificationError as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "configuration": configuration,
                    "failed_case": error.case_id,
                    "error_category": error.code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"success": False, "error_category": "interrupted"}))
        return 130
    except Exception as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "configuration": configuration,
                    "error_category": f"unexpected_{type(error).__name__}",
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
