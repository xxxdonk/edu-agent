from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import ApiModel, ResourceType, utc_now


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentRun(ApiModel):
    agent: str
    resource_type: ResourceType | None = None
    status: AgentRunStatus = AgentRunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class TaskState(ApiModel):
    task_id: str
    task_type: Literal["resource_generation", "evaluation"]
    student_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = Field(default=0, ge=0, le=100)
    current_stage: str
    requested_resource_types: list[ResourceType] = Field(default_factory=list)
    result_resource_ids: list[str] = Field(default_factory=list)
    agent_runs: list[AgentRun] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskEvent(ApiModel):
    event_id: str
    task_id: str
    sequence: int = Field(ge=1)
    event_type: Literal["task", "agent", "review", "heartbeat"]
    status: str
    progress: int = Field(ge=0, le=100)
    message: str
    agent: str | None = None
    resource_type: ResourceType | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TaskAcceptedResponse(ApiModel):
    task_id: str
    status: TaskStatus
    status_url: str
    events_url: str
