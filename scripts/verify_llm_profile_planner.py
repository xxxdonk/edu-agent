from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.llm import (  # noqa: E402
    LLMConfigurationError,
    LLMError,
    LLMNetworkError,
    LLMResponseFormatError,
    LLMSafetyRefusalError,
    LLMServerError,
    LLMTimeoutError,
    LLMValidationError,
    build_llm_client,
)
from app.planner import DevelopmentPlannerAgent, PlannerAgent  # noqa: E402
from app.profile import DevelopmentProfileAgent, ProfileAgent  # noqa: E402
from app.schemas.profile import ChatMessage, ProfileChatRequest  # noqa: E402


COMPLETE_CASE = """我是人工智能专业的学生，刚开始学习机器学习，数学基础比较一般。
我想理解支持向量机，并且最后能使用Python完成一个简单分类项目。
我比较喜欢图示、生活中的类比和代码案例，每天大概能学习30分钟。"""

INCOMPLETE_CASE = "我最近想学习机器学习，但是还不知道应该从哪里开始。"


def _load_and_validate_configuration() -> tuple[Settings | None, list[str]]:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return None, [".env（请从 .env.example 复制）"]

    load_dotenv(dotenv_path=env_path, override=False)
    missing: list[str] = []
    if os.getenv("ENABLE_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        missing.append("ENABLE_LLM=true")
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        if not os.getenv(name, "").strip():
            missing.append(name)
    if missing:
        return None, missing
    try:
        return Settings.from_env(), []
    except ValueError as error:
        return None, [f"环境变量格式错误：{error}"]


def _error_category(error: BaseException | None) -> str | None:
    if error is None:
        return None
    if isinstance(error, LLMError):
        return error.code
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.HTTPError):
        return "network_error"
    if isinstance(error, ValidationError):
        return "pydantic_validation_error"
    if isinstance(error, ValueError):
        return "value_error"
    return "unexpected_error"


def _stage_summary(
    *,
    case_name: str,
    agent: str,
    success: bool,
    fallback: bool,
    error: BaseException | None,
    elapsed_ms: float,
) -> dict[str, object]:
    return {
        "case": case_name,
        "agent": agent,
        "success": success,
        "fallback": fallback,
        "error_category": _error_category(error),
        "elapsed_ms": round(elapsed_ms, 1),
    }


async def _run_case(
    *,
    case_name: str,
    student_id: str,
    content: str,
    profile_agent: ProfileAgent,
    planner_agent: PlannerAgent,
) -> dict[str, object]:
    request = ProfileChatRequest(
        student_id=student_id,
        conversation_id=f"manual-{case_name}",
        messages=[
            ChatMessage(
                message_id=f"manual-{case_name}-message-1",
                role="user",
                content=content,
            )
        ],
    )

    profile_started = time.perf_counter()
    profile_error: BaseException | None = None
    try:
        profile_response = await profile_agent.extract(request, previous=None)
    except Exception as error:  # manual boundary: never emit a traceback
        profile_error = error
        profile_response = DevelopmentProfileAgent().extract(request, previous=None)
    profile_elapsed_ms = (time.perf_counter() - profile_started) * 1000
    profile_fallback = profile_response.extraction_mode != "llm_structured"

    planner_started = time.perf_counter()
    planner_error: BaseException | None = None
    try:
        path = await planner_agent.generate(profile_response.profile)
    except Exception as error:  # manual boundary: keep the next case runnable
        planner_error = error
        path = DevelopmentPlannerAgent().generate(profile_response.profile)
    planner_elapsed_ms = (time.perf_counter() - planner_started) * 1000
    planner_fallback = path.generation_mode != "llm_structured"

    return {
        "case": case_name,
        "extraction_mode": profile_response.extraction_mode,
        "generation_mode": path.generation_mode,
        "missing_dimensions": profile_response.missing_dimensions,
        "next_question": profile_response.next_question,
        "path_topics": [step.topic for step in path.steps],
        "fallback": profile_fallback or planner_fallback,
        "stages": [
            _stage_summary(
                case_name=case_name,
                agent="profile",
                success=True,
                fallback=profile_fallback,
                error=profile_error,
                elapsed_ms=profile_elapsed_ms,
            ),
            _stage_summary(
                case_name=case_name,
                agent="planner",
                success=True,
                fallback=planner_fallback,
                error=planner_error,
                elapsed_ms=planner_elapsed_ms,
            ),
        ],
    }


def _failed_case_summary(case_name: str, error: BaseException) -> dict[str, object]:
    return {
        "case": case_name,
        "extraction_mode": None,
        "generation_mode": None,
        "missing_dimensions": [],
        "next_question": None,
        "path_topics": [],
        "fallback": True,
        "stages": [
            _stage_summary(
                case_name=case_name,
                agent="case_runner",
                success=False,
                fallback=True,
                error=error,
                elapsed_ms=0.0,
            )
        ],
    }


async def main() -> int:
    settings, missing = _load_and_validate_configuration()
    if missing:
        print("无法开始真实模型验证，缺少或无效的配置：")
        for item in missing:
            print(f"- {item}")
        print("不会尝试网络请求，也不会输出任何密钥。")
        return 2

    assert settings is not None
    try:
        client = build_llm_client(settings.llm)
    except (
        LLMConfigurationError,
        LLMNetworkError,
        LLMTimeoutError,
        LLMServerError,
        LLMSafetyRefusalError,
        LLMResponseFormatError,
        LLMValidationError,
        httpx.HTTPError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "provider": settings.llm.provider,
                    "model": settings.llm.model,
                    "success": False,
                    "error_category": _error_category(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "provider": settings.llm.provider,
                    "model": settings.llm.model,
                    "success": False,
                    "error_category": _error_category(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if client is None:
        print("LLM 未启用，请在 .env 中设置 ENABLE_LLM=true。")
        return 2

    profile_agent = ProfileAgent(client, enable_llm=True)
    planner_agent = PlannerAgent(client, enable_llm=True)
    cases = []
    for case_name, student_id, content in (
        ("complete_profile", "manual-complete", COMPLETE_CASE),
        ("incomplete_profile", "manual-incomplete", INCOMPLETE_CASE),
    ):
        try:
            cases.append(
                await _run_case(
                    case_name=case_name,
                    student_id=student_id,
                    content=content,
                    profile_agent=profile_agent,
                    planner_agent=planner_agent,
                )
            )
        except Exception as error:  # one case must not stop the next one
            cases.append(_failed_case_summary(case_name, error))

    summary = {
        "provider": settings.llm.provider,
        "model": settings.llm.model,
        "cases": cases,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    all_stages_succeeded = all(
        all(stage.get("success") for stage in case.get("stages", []))
        for case in cases
    )
    return 0 if all_stages_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
