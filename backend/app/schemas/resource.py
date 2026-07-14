from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .common import ApiModel, Difficulty, ResourceType, utc_now


class SourceReference(ApiModel):
    source_id: str
    title: str
    locator: str
    chunk_id: str | None = None


class Resource(ApiModel):
    resource_id: str
    resource_type: ResourceType
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    content_format: Literal["markdown", "mermaid", "json", "python", "text"]
    target_topic: str = Field(min_length=1, max_length=300)
    difficulty: Difficulty
    personalization_reason: str = Field(min_length=1, max_length=2000)
    source_references: list[SourceReference] = Field(min_length=1)
    review_status: Literal["pending", "approved", "rejected", "needs_revision"]
    created_at: datetime = Field(default_factory=utc_now)


class ResourceGenerationRequest(ApiModel):
    student_id: str = Field(min_length=1, max_length=128)
    path_id: str = Field(min_length=1)
    step: int = Field(ge=1)
    resource_types: list[ResourceType] = Field(
        default_factory=lambda: list(ResourceType), min_length=1
    )
    regenerate: bool = False

    @field_validator("resource_types")
    @classmethod
    def resource_types_must_be_unique(
        cls, resource_types: list[ResourceType]
    ) -> list[ResourceType]:
        if len(resource_types) != len(set(resource_types)):
            raise ValueError("resource_types must not contain duplicates")
        return resource_types
