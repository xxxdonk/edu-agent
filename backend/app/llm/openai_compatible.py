from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from .contracts import LLMMessage, StructuredModel
from .errors import (
    LLMConfigurationError,
    LLMError,
    LLMNetworkError,
    LLMResponseFormatError,
    LLMSafetyRefusalError,
    LLMServerError,
    LLMTimeoutError,
    LLMValidationError,
)


class OpenAICompatibleLLMClient:
    """Vendor-neutral adapter for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("LLM_API_KEY is not configured")
        if not model:
            raise LLMConfigurationError("LLM_MODEL is not configured")
        if not base_url:
            raise LLMConfigurationError("LLM_BASE_URL is not configured")
        if timeout_seconds <= 0:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be positive")
        if max_retries < 0 or max_retries > 3:
            raise LLMConfigurationError("LLM_MAX_RETRIES must be between 0 and 3")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        timeout_seconds: float | None = None,
    ) -> StructuredModel:
        schema_text = json.dumps(
            response_model.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        effective_prompt = (
            f"{system_prompt}\n\n"
            "Return exactly one JSON object. Do not use Markdown fences. "
            f"The JSON must satisfy this schema: {schema_text}"
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": effective_prompt},
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        timeout = timeout_seconds or self._timeout_seconds

        for attempt in range(self._max_retries + 1):
            try:
                response_body = await self._post(payload, timeout)
                return self._parse_response(response_body, response_model)
            except LLMError as error:
                if not error.retryable or attempt >= self._max_retries:
                    raise
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        raise LLMServerError("structured generation exhausted retry attempts")

    async def _post(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as error:
            raise LLMTimeoutError("LLM request timed out") from error
        except httpx.RequestError as error:
            raise LLMNetworkError("LLM network request failed") from error

        if response.status_code >= 400:
            error_code = self._error_code(response)
            if error_code in {"content_filter", "data_inspection_failed", "safety_refusal"}:
                raise LLMSafetyRefusalError("LLM provider rejected content for safety")
            if response.status_code == 408:
                raise LLMTimeoutError("LLM provider timed out")
            if response.status_code == 429 or response.status_code >= 500:
                raise LLMServerError(
                    f"LLM provider returned retryable status {response.status_code}"
                )
            raise LLMServerError(
                f"LLM provider returned status {response.status_code}",
                retryable=False,
            )
        try:
            body = response.json()
        except ValueError as error:
            raise LLMResponseFormatError("LLM response body is not JSON") from error
        if not isinstance(body, dict):
            raise LLMResponseFormatError("LLM response body must be an object")
        return body

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        error = body.get("error")
        return str(error.get("code")) if isinstance(error, dict) and error.get("code") else None

    @staticmethod
    def _parse_response(
        body: dict[str, Any], response_model: type[StructuredModel]
    ) -> StructuredModel:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseFormatError("LLM response has no choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMResponseFormatError("LLM response choice is invalid")
        if choice.get("finish_reason") == "content_filter":
            raise LLMSafetyRefusalError("LLM provider rejected content for safety")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise LLMResponseFormatError("LLM response message is invalid")
        if message.get("refusal"):
            raise LLMSafetyRefusalError("LLM provider refused structured generation")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseFormatError("LLM response content is empty")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise LLMResponseFormatError("LLM response content is not valid JSON") from error
        try:
            return response_model.model_validate(parsed)
        except ValidationError as error:
            raise LLMValidationError(
                "LLM response failed Pydantic validation"
            ) from error
