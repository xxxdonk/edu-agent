from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import BaseModel

from app.llm import (
    LLMMessage,
    LLMResponseFormatError,
    LLMSafetyRefusalError,
    LLMServerError,
    LLMValidationError,
)
from app.llm.openai_compatible import OpenAICompatibleLLMClient
from app.profile import ProfileAgent
from app.schemas.profile import ChatMessage, ProfileChatRequest


class ResponsePayload(BaseModel):
    value: int


def _body(
    content: str | None = '{"value":1}',
    *,
    finish_reason: str = "stop",
) -> dict:
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": content},
            }
        ]
    }


def _parse(body: dict) -> ResponsePayload:
    result = OpenAICompatibleLLMClient._parse_response(body, ResponsePayload)
    assert isinstance(result, ResponsePayload)
    return result


def _client(
    handler,
    *,
    max_retries: int = 1,
) -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(
        api_key="test-key-not-real",
        model="test-model",
        base_url="https://example.invalid/v1",
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def _generate(client: OpenAICompatibleLLMClient) -> ResponsePayload:
    result = asyncio.run(
        client.generate_structured(
            system_prompt="Return structured test data.",
            messages=[LLMMessage(role="user", content="test")],
            response_model=ResponsePayload,
        )
    )
    assert isinstance(result, ResponsePayload)
    return result


def test_pure_json_is_parsed() -> None:
    assert _parse(_body('{"value":7}')).value == 7


def test_markdown_json_fence_is_parsed() -> None:
    assert _parse(_body('```json\n{"value":8}\n```')).value == 8


def test_explanation_around_json_is_rejected() -> None:
    with pytest.raises(LLMResponseFormatError):
        _parse(_body('Here is the result: {"value":9} Thanks.'))


def test_empty_content_is_rejected() -> None:
    with pytest.raises(LLMResponseFormatError):
        _parse(_body(""))


def test_missing_choices_is_rejected() -> None:
    with pytest.raises(LLMResponseFormatError):
        _parse({})


def test_missing_message_is_rejected() -> None:
    with pytest.raises(LLMResponseFormatError):
        _parse({"choices": [{"finish_reason": "stop"}]})


def test_message_refusal_is_rejected() -> None:
    body = _body()
    body["choices"][0]["message"]["refusal"] = "request refused"
    with pytest.raises(LLMSafetyRefusalError):
        _parse(body)


def test_finish_reason_length_is_rejected_before_valid_json_parse() -> None:
    with pytest.raises(LLMResponseFormatError, match="truncated"):
        _parse(_body('{"value":10}', finish_reason="length"))


def test_finish_reason_length_triggers_profile_development_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_body('{"otherwise":"valid-json"}', finish_reason="length"),
        )

    request = ProfileChatRequest(
        student_id="truncated-response-student",
        messages=[
            ChatMessage(
                message_id="message-1",
                role="user",
                content="我是人工智能专业学生，刚开始学习机器学习。",
            )
        ],
    )
    response = asyncio.run(
        ProfileAgent(_client(handler, max_retries=0), enable_llm=True).extract(
            request,
            previous=None,
        )
    )
    assert response.extraction_mode == "development_heuristic"


def test_http_429_retries_only_configured_number_of_times() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"code": "rate_limit"}})

    with pytest.raises(LLMServerError):
        _generate(_client(handler, max_retries=1))
    assert calls == 2


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_http_5xx_retries_only_configured_number_of_times(
    status_code: int,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"error": {"code": "server_error"}})

    with pytest.raises(LLMServerError):
        _generate(_client(handler, max_retries=2))
    assert calls == 3


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(LLMResponseFormatError):
        _parse(_body("{invalid-json"))


def test_pydantic_validation_failure_is_rejected() -> None:
    with pytest.raises(LLMValidationError):
        _parse(_body('{"value":"not-an-integer"}'))
