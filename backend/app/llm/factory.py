from __future__ import annotations

from app.config import LLMSettings

from .contracts import LLMClient
from .errors import LLMConfigurationError
from .openai_compatible import OpenAICompatibleLLMClient


def build_llm_client(settings: LLMSettings) -> LLMClient | None:
    if not settings.enabled:
        return None
    if settings.provider not in {"openai_compatible", "dashscope"}:
        raise LLMConfigurationError(
            f"unsupported LLM_PROVIDER: {settings.provider}"
        )
    return OpenAICompatibleLLMClient(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )
