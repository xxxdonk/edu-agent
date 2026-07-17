from __future__ import annotations

import logging
from pathlib import Path

from app import config
from app.config import LLMSettings, Settings
from app.main import create_app


LLM_ENV_NAMES = (
    "ENABLE_LLM",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
)


def test_settings_from_env_loads_project_root_dotenv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "ENABLE_LLM=true",
                "LLM_PROVIDER=openai_compatible",
                "LLM_API_KEY=test-secret",
                "LLM_MODEL=test-model",
                "LLM_BASE_URL=https://example.invalid/v1",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_project_root", lambda: tmp_path)
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.llm.enabled is True
    assert settings.llm.provider == "openai_compatible"
    assert settings.llm.model == "test-model"
    assert settings.llm.api_key == "test-secret"


def test_settings_from_env_does_not_override_process_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "ENABLE_LLM=true\nLLM_MODEL=dotenv-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_project_root", lambda: tmp_path)
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENABLE_LLM", "false")
    monkeypatch.setenv("LLM_MODEL", "process-model")

    settings = Settings.from_env()

    assert settings.llm.enabled is False
    assert settings.llm.model == "process-model"


def test_create_app_startup_log_never_contains_key_or_base_url(
    caplog,
    tmp_path: Path,
) -> None:
    api_key = "never-log-this-key"
    base_url = "https://never-log-this-host.invalid/v1"
    settings = Settings(
        environment="test",
        host="127.0.0.1",
        port=8000,
        database_path=tmp_path / "startup-log.db",
        allowed_origins=("http://localhost:5173",),
        profile_mode="development_heuristic",
        planner_mode="development_rule_based",
        llm=LLMSettings(
            enabled=True,
            provider="openai_compatible",
            api_key=api_key,
            model="safe-model-name",
            base_url=base_url,
        ),
    )
    caplog.set_level(logging.WARNING, logger="app.main")

    create_app(settings)

    messages = [record.getMessage() for record in caplog.records if record.name == "app.main"]
    startup_message = next(message for message in messages if message.startswith("ENABLE_LLM="))
    assert startup_message == (
        "ENABLE_LLM=True provider=openai_compatible "
        "model=safe-model-name api_key_present=True"
    )
    assert api_key not in caplog.text
    assert base_url not in caplog.text
