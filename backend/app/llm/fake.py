from __future__ import annotations

import json
from collections import deque
from typing import Any

from pydantic import BaseModel, ValidationError

from .contracts import LLMMessage, StructuredModel
from .errors import LLMResponseFormatError, LLMValidationError


class FakeLLMClient:
    """Deterministic, network-free structured client for automated tests."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses = deque(responses or [])
        self.calls: list[dict[str, Any]] = []

    def enqueue(self, response: Any) -> None:
        self._responses.append(response)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        timeout_seconds: float | None = None,
    ) -> StructuredModel:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "messages": list(messages),
                "response_model": response_model,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self._responses:
            raise LLMResponseFormatError("FakeLLMClient has no queued response")
        response = self._responses.popleft()
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, BaseModel):
            response = response.model_dump(mode="json")
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError as error:
                raise LLMResponseFormatError("fake response is not valid JSON") from error
        try:
            return response_model.model_validate(response)
        except ValidationError as error:
            raise LLMValidationError(
                "fake response failed Pydantic validation"
            ) from error
