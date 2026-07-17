from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_TYPES = ("quiz", "reading", "mind_map")
TERMINAL_STATUSES = {"completed", "partial_success", "failed"}
ACCEPTANCE_TEXT = (
    "我是人工智能专业大二学生，目前在学习机器学习，"
    "数学基础一般，梯度下降一直没弄懂，希望完成一个分类项目。"
    "我每天可以学习45分钟，偏好代码案例和图示。"
)


class StabilityError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _load_configuration() -> dict[str, object]:
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
        raise StabilityError("real_llm_configuration_missing")
    return {
        "ENABLE_LLM": True,
        "provider": provider,
        "model": model,
        "api_key_present": key_present,
    }


class ResourceStabilityVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: float,
        task_timeout_seconds: float,
        poll_interval_seconds: float,
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
                "User-Agent": "EduAgent-Resource-Stability-Verifier/1.0",
            },
        )
        self.task_timeout_seconds = task_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def close(self) -> None:
        self.client.close()

    def _request(
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
            raise StabilityError("http_timeout") from error
        except httpx.HTTPError as error:
            raise StabilityError("http_transport_error") from error
        if response.status_code != expected_status:
            raise StabilityError(f"unexpected_http_status_{response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise StabilityError("response_not_json") from error
        if not isinstance(body, dict):
            raise StabilityError("response_not_object")
        return body

    def _wait_task(self, status_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout_seconds
        while time.monotonic() < deadline:
            task = self._request("GET", status_url, expected_status=200)
            if task.get("status") in TERMINAL_STATUSES:
                return task
            time.sleep(self.poll_interval_seconds)
        raise StabilityError("resource_task_timeout")

    def run(self, runs: int) -> dict[str, Any]:
        health = self._request("GET", "/api/health", expected_status=200)
        if health.get("status") != "ok":
            raise StabilityError("health_not_ok")

        student_id = f"stability-{uuid4().hex}"
        profile_response = self._request(
            "POST",
            "/api/profile/chat",
            expected_status=200,
            payload={
                "student_id": student_id,
                "conversation_id": f"conversation-{uuid4().hex}",
                "messages": [
                    {
                        "message_id": f"message-{uuid4().hex}",
                        "role": "user",
                        "content": ACCEPTANCE_TEXT,
                    }
                ],
                "evaluation_summary": None,
            },
        )
        if profile_response.get("extraction_mode") != "llm_structured":
            raise StabilityError("profile_not_llm_structured")
        profile = profile_response.get("profile")
        if not isinstance(profile, dict):
            raise StabilityError("profile_missing")

        path_response = self._request(
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
        path = path_response.get("path")
        if not isinstance(path, dict) or path.get("generation_mode") != "llm_structured":
            raise StabilityError("planner_not_llm_structured")
        steps = path.get("steps")
        if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
            raise StabilityError("path_steps_missing")

        attempts: dict[str, int] = defaultdict(int)
        llm_successes: dict[str, int] = defaultdict(int)
        fallbacks: dict[str, int] = defaultdict(int)
        reviewer_approved: dict[str, int] = defaultdict(int)
        run_summaries: list[dict[str, Any]] = []

        for run_number in range(1, runs + 1):
            started = time.perf_counter()
            accepted = self._request(
                "POST",
                "/api/resources/generate",
                expected_status=202,
                payload={
                    "student_id": student_id,
                    "path_id": path["path_id"],
                    "step": steps[0]["step"],
                    "resource_types": list(TARGET_TYPES),
                    "regenerate": True,
                },
            )
            task = self._wait_task(str(accepted["status_url"]))
            resource_ids = task.get("result_resource_ids")
            if not isinstance(resource_ids, list):
                resource_ids = []
            resources = [
                self._request(
                    "GET",
                    f"/api/resources/{resource_id}",
                    expected_status=200,
                )
                for resource_id in resource_ids
            ]
            by_type = {
                str(resource.get("resource_type")): resource for resource in resources
            }
            run_fallback_types: list[str] = []
            missing_types: list[str] = []
            for resource_type in TARGET_TYPES:
                attempts[resource_type] += 1
                resource = by_type.get(resource_type)
                if resource is None:
                    missing_types.append(resource_type)
                    continue
                reason = str(resource.get("personalization_reason", ""))
                if "development fallback" in reason:
                    fallbacks[resource_type] += 1
                    run_fallback_types.append(resource_type)
                else:
                    llm_successes[resource_type] += 1
                if resource.get("review_status") == "approved":
                    reviewer_approved[resource_type] += 1
            run_summaries.append(
                {
                    "run": run_number,
                    "task_status": task.get("status"),
                    "resource_count": len(resources),
                    "fallback_types": sorted(run_fallback_types),
                    "missing_types": sorted(missing_types),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )

        agents = {
            resource_type: {
                "attempts": attempts[resource_type],
                "llm_successes": llm_successes[resource_type],
                "fallbacks": fallbacks[resource_type],
                "reviewer_approved": reviewer_approved[resource_type],
                "llm_success_rate": round(
                    llm_successes[resource_type] / max(attempts[resource_type], 1),
                    4,
                ),
            }
            for resource_type in TARGET_TYPES
        }
        goal_met = all(
            result["llm_successes"] == runs
            and result["reviewer_approved"] == runs
            for result in agents.values()
        )
        return {
            "success": True,
            "goal_met": goal_met,
            "profile_mode": profile_response.get("extraction_mode"),
            "planner_mode": path.get("generation_mode"),
            "cache_bypassed": True,
            "runs": run_summaries,
            "agents": agents,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure real Quiz, Reading, and MindMap LLM success across repeated "
            "cache-bypassed resource tasks without printing model responses."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--request-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--task-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        args.runs < 3
        or args.request_timeout_seconds <= 0
        or args.task_timeout_seconds <= 0
        or args.poll_interval_seconds <= 0
    ):
        print(
            json.dumps(
                {"success": False, "error_category": "invalid_arguments"},
                ensure_ascii=False,
            )
        )
        return 2
    try:
        configuration = _load_configuration()
    except StabilityError as error:
        print(
            json.dumps(
                {"success": False, "error_category": error.code},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    verifier = ResourceStabilityVerifier(
        base_url=args.base_url,
        request_timeout_seconds=args.request_timeout_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    try:
        summary = verifier.run(args.runs)
        summary["configuration"] = configuration
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["goal_met"] else 1
    except StabilityError as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "configuration": configuration,
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
