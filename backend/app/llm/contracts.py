from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


class LLMClient(Protocol):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        timeout_seconds: float | None = None,
    ) -> StructuredModel:
        """Generate one response and validate it against response_model."""
