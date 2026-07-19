from __future__ import annotations

import hashlib
import logging
import sqlite3
from typing import Any
from uuid import uuid4

from app.schemas import LearningPath, Resource, StudentProfile, TaskEvent, TaskState
from app.schemas.common import ResourceType, utc_now

from .sqlite import SQLiteDatabase

logger = logging.getLogger(__name__)


def safe_student_reference(student_id: str) -> str:
    """Return a stable, non-reversible identifier suitable for logs."""

    return hashlib.sha256(student_id.encode("utf-8")).hexdigest()[:12]


class Repository:
    _profile_version_conflict_retries = 1

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save_profile(self, profile: StudentProfile) -> StudentProfile:
        """Atomically allocate and persist the next profile version.

        Profile extraction can be slow, so it deliberately happens before this
        short write transaction. The repository is the sole authority for the
        persisted version number.
        """

        student_ref = safe_student_reference(profile.student_id)
        logger.info("profile_persist_started student_ref=%s", student_ref)
        attempted_version = profile.version
        for retry_attempt in range(self._profile_version_conflict_retries + 1):
            try:
                with self.database.connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    row = connection.execute(
                        """
                        SELECT version, profile_json FROM profiles
                        WHERE student_id = ?
                        ORDER BY version DESC LIMIT 1
                        """,
                        (profile.student_id,),
                    ).fetchone()
                    latest = (
                        StudentProfile.model_validate_json(row["profile_json"])
                        if row
                        else None
                    )
                    if (
                        latest is not None
                        and profile.version <= latest.version
                        and self._same_profile_content(latest, profile)
                    ):
                        logger.info(
                            "profile_persist_completed student_ref=%s version=%s deduplicated=true",
                            student_ref,
                            latest.version,
                        )
                        return latest

                    attempted_version = int(row["version"]) + 1 if row else 1
                    persisted = profile.model_copy(
                        deep=True,
                        update={"version": attempted_version},
                    )
                    logger.info(
                        "profile_version_allocated student_ref=%s version=%s retry_attempt=%s",
                        student_ref,
                        attempted_version,
                        retry_attempt,
                    )
                    connection.execute(
                        """
                        INSERT INTO profiles(student_id, version, profile_json, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            persisted.student_id,
                            persisted.version,
                            persisted.model_dump_json(),
                            persisted.updated_at.isoformat(),
                        ),
                    )
                logger.info(
                    "profile_persist_completed student_ref=%s version=%s deduplicated=false",
                    student_ref,
                    persisted.version,
                )
                return persisted
            except sqlite3.IntegrityError as error:
                if not self._is_profile_version_conflict(error):
                    raise
                logger.warning(
                    "profile_version_conflict student_ref=%s attempted_version=%s retry_attempt=%s",
                    student_ref,
                    attempted_version,
                    retry_attempt,
                )
                if retry_attempt >= self._profile_version_conflict_retries:
                    raise
                logger.info(
                    "profile_version_retry student_ref=%s attempted_version=%s retry_attempt=%s",
                    student_ref,
                    attempted_version,
                    retry_attempt + 1,
                )
        raise RuntimeError("profile persistence retry loop exhausted")

    @staticmethod
    def _same_profile_content(left: StudentProfile, right: StudentProfile) -> bool:
        left_content = left.model_dump(mode="json")
        right_content = right.model_dump(mode="json")
        for content in (left_content, right_content):
            content.pop("version", None)
            content.pop("updated_at", None)
        return left_content == right_content

    @staticmethod
    def _is_profile_version_conflict(error: sqlite3.IntegrityError) -> bool:
        return (
            "UNIQUE constraint failed: profiles.student_id, profiles.version"
            in str(error)
        )

    def get_latest_profile(self, student_id: str) -> StudentProfile | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT profile_json FROM profiles
                WHERE student_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (student_id,),
            ).fetchone()
        return StudentProfile.model_validate_json(row["profile_json"]) if row else None

    def save_path(self, path: LearningPath) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO learning_paths(path_id, student_id, profile_version, path_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    path.path_id,
                    path.student_id,
                    path.profile_version,
                    path.model_dump_json(),
                    path.created_at.isoformat(),
                ),
            )

    def get_path(self, path_id: str) -> LearningPath | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT path_json FROM learning_paths WHERE path_id = ?",
                (path_id,),
            ).fetchone()
        return LearningPath.model_validate_json(row["path_json"]) if row else None

    def save_resource(self, resource: Resource, task_id: str | None = None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO resources(
                    resource_id, task_id, resource_type, resource_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    resource.resource_id,
                    task_id,
                    resource.resource_type.value,
                    resource.model_dump_json(),
                    resource.created_at.isoformat(),
                ),
            )

    def get_resource(self, resource_id: str) -> Resource | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT resource_json FROM resources WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
        return Resource.model_validate_json(row["resource_json"]) if row else None

    def save_task(self, task: TaskState) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, task_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_json = excluded.task_json,
                    updated_at = excluded.updated_at
                """,
                (
                    task.task_id,
                    task.model_dump_json(),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )

    def get_task(self, task_id: str) -> TaskState | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT task_json FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return TaskState.model_validate_json(row["task_json"]) if row else None

    def append_event(
        self,
        task_id: str,
        *,
        event_type: str,
        status: str,
        progress: int,
        message: str,
        agent: str | None = None,
        resource_type: ResourceType | None = None,
        error: str | None = None,
    ) -> TaskEvent:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM task_events WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            event = TaskEvent(
                event_id=str(uuid4()),
                task_id=task_id,
                sequence=int(row["next_sequence"]),
                event_type=event_type,
                status=status,
                progress=progress,
                message=message,
                agent=agent,
                resource_type=resource_type,
                error=error,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO task_events(task_id, sequence, event_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, event.sequence, event.model_dump_json(), now.isoformat()),
            )
        return event

    def list_events(self, task_id: str, after_sequence: int = 0) -> list[TaskEvent]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM task_events
                WHERE task_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (task_id, after_sequence),
            ).fetchall()
        return [TaskEvent.model_validate_json(row["event_json"]) for row in rows]
