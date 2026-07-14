from __future__ import annotations

import os
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    host: str
    port: int
    database_path: Path
    allowed_origins: tuple[str, ...]
    profile_mode: str
    planner_mode: str

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
        )
