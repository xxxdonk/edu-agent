from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("DATABASE_URL currently supports only sqlite:/// URLs")
    raw_path = database_url[len(prefix) :]
    if not raw_path:
        raise ValueError("DATABASE_URL must include a SQLite database path")
    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = _project_root() / database_path
    return database_path.resolve()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class LLMSettings:
    enabled: bool = False
    provider: str = "openai_compatible"
    api_key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 30.0
    max_retries: int = 1


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    host: str
    port: int
    database_path: Path
    allowed_origins: tuple[str, ...]
    profile_mode: str
    planner_mode: str
    llm: LLMSettings = field(default_factory=LLMSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL", "sqlite:///./data/eduagent.db")
        database_path = _sqlite_path(database_url)

        origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "EDUAGENT_ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        )
        return cls(
            environment=os.getenv("EDUAGENT_ENV", "development"),
            host=os.getenv("EDUAGENT_HOST", "127.0.0.1"),
            port=int(os.getenv("EDUAGENT_PORT", "8000")),
            database_path=database_path,
            allowed_origins=origins,
            profile_mode=os.getenv("EDUAGENT_PROFILE_MODE", "development_heuristic"),
            planner_mode=os.getenv("EDUAGENT_PLANNER_MODE", "development_rule_based"),
            llm=LLMSettings(
                enabled=_env_bool("ENABLE_LLM", False),
                provider=os.getenv("LLM_PROVIDER", "openai_compatible").strip().lower(),
                api_key=os.getenv("LLM_API_KEY", ""),
                model=os.getenv("LLM_MODEL", ""),
                base_url=os.getenv("LLM_BASE_URL", ""),
                timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
                max_retries=int(os.getenv("LLM_MAX_RETRIES", "1")),
            ),
        )
