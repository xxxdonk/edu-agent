from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.schemas import LearningPath, Resource, StudentProfile, TaskEvent, TaskState
from app.schemas.common import ResourceType, utc_now

from .sqlite import SQLiteDatabase


class Repository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save_profile(self, profile: StudentProfile) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO profiles(student_id, version, profile_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    profile.student_id,
                    profile.version,
                    profile.model_dump_json(),
                    profile.updated_at.isoformat(),
                ),
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
