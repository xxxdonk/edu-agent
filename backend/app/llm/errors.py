from __future__ import annotations


class LLMError(Exception):
    code = "llm_error"
    retryable = False

    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message


class LLMConfigurationError(LLMError):
    code = "configuration_missing"


class LLMNetworkError(LLMError):
    code = "network_error"
    retryable = True


class LLMTimeoutError(LLMError):
    code = "timeout"
    retryable = True


class LLMServerError(LLMError):
    code = "server_error"
    retryable = True

    def __init__(self, safe_message: str, *, retryable: bool = True) -> None:
        super().__init__(safe_message)
        self.retryable = retryable


class LLMSafetyRefusalError(LLMError):
    code = "safety_refusal"


class LLMResponseFormatError(LLMError):
    code = "response_format_error"


class LLMValidationError(LLMError):
    code = "pydantic_validation_error"


def safe_error_summary(error: BaseException) -> str:
    if isinstance(error, LLMError):
        return f"{error.code}: {error.safe_message}"
    return f"{type(error).__name__}: unexpected structured generation failure"
