from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from app.schemas import Resource, ResourceType
from app.schemas.common import utc_now

from .contracts import SharedAgentContext


_GENERATOR_REVISIONS: dict[ResourceType, str] = {
    ResourceType.EXPLANATION: "explanation-phase5-v1",
    ResourceType.MIND_MAP: "mind-map-phase5-v1",
    ResourceType.QUIZ: "quiz-phase5-v1",
    ResourceType.READING: "reading-phase5-v1",
    ResourceType.CODING: "coding-phase5-v1",
}


def _fingerprint(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ResourceCacheKey:
    student_id: str
    profile_version: int
    profile_fingerprint: str
    path_id: str
    step: int
    step_fingerprint: str
    resource_type: ResourceType
    model_identity: str
    knowledge_base_version: str
    generator_revision: str

    @classmethod
    def from_context(
        cls,
        context: SharedAgentContext,
        resource_type: ResourceType,
        *,
        model_identity: str,
        knowledge_base_version: str,
    ) -> "ResourceCacheKey":
        step = next(
            (item for item in context.path.steps if item.step == context.request.step),
            None,
        )
        if step is None:
            raise ValueError(f"path step not found: {context.request.step}")
        return cls(
            student_id=context.request.student_id,
            profile_version=context.profile.version,
            profile_fingerprint=_fingerprint(
                context.profile.model_dump(mode="json", exclude={"updated_at"})
            ),
            path_id=context.path.path_id,
            step=context.request.step,
            step_fingerprint=_fingerprint(step.model_dump(mode="json")),
            resource_type=resource_type,
            model_identity=model_identity,
            knowledge_base_version=knowledge_base_version,
            generator_revision=_GENERATOR_REVISIONS[resource_type],
        )

    @property
    def digest(self) -> str:
        return _fingerprint(
            {
                "student_id": self.student_id,
                "profile_version": self.profile_version,
                "profile_fingerprint": self.profile_fingerprint,
                "path_id": self.path_id,
                "step": self.step,
                "step_fingerprint": self.step_fingerprint,
                "resource_type": self.resource_type.value,
                "model_identity": self.model_identity,
                "knowledge_base_version": self.knowledge_base_version,
                "generator_revision": self.generator_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class ResourceCacheStats:
    hits: int
    misses: int
    writes: int
    evictions: int
    expirations: int
    invalidations: int
    entries: int


@dataclass(slots=True)
class _CacheEntry:
    resource: Resource
    expires_at: float


class ResourceCache:
    """Thread-safe, process-local bounded cache for approved resources."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        ttl_seconds: float = 1800.0,
        max_entries: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("resource cache ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("resource cache max_entries must be positive")
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[ResourceCacheKey, _CacheEntry] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._evictions = 0
        self._expirations = 0
        self._invalidations = 0

    def get(self, key: ResourceCacheKey) -> Resource | None:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                self._misses += 1
                self._expirations += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return entry.resource.model_copy(deep=True)

    def put(self, key: ResourceCacheKey, resource: Resource) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._purge_expired_locked()
            if key in self._entries:
                del self._entries[key]
            while len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1
            self._entries[key] = _CacheEntry(
                resource=resource.model_copy(deep=True),
                expires_at=self._clock() + self.ttl_seconds,
            )
            self._writes += 1

    def invalidate(self, key: ResourceCacheKey) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            removed = self._entries.pop(key, None) is not None
            if removed:
                self._invalidations += 1
            return removed

    def clear(self) -> None:
        with self._lock:
            self._invalidations += len(self._entries)
            self._entries.clear()

    @property
    def stats(self) -> ResourceCacheStats:
        with self._lock:
            self._purge_expired_locked()
            return ResourceCacheStats(
                hits=self._hits,
                misses=self._misses,
                writes=self._writes,
                evictions=self._evictions,
                expirations=self._expirations,
                invalidations=self._invalidations,
                entries=len(self._entries),
            )

    def _purge_expired_locked(self) -> None:
        now = self._clock()
        expired = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired:
            del self._entries[key]
        self._expirations += len(expired)


def is_cacheable_resource(resource: Resource) -> bool:
    if resource.review_status != "approved":
        return False
    if "development fallback" in resource.personalization_reason.casefold():
        return False
    if resource.resource_type != ResourceType.QUIZ:
        return True
    if resource.content_format != "json":
        return False
    try:
        document = json.loads(resource.content)
    except json.JSONDecodeError:
        return False
    questions = document.get("questions") if isinstance(document, dict) else None
    return bool(
        isinstance(questions, list)
        and questions
        and all(
            isinstance(question, dict) and str(question.get("id") or "").strip()
            for question in questions
        )
    )


def clone_cached_resource(resource: Resource) -> Resource:
    new_resource_id = str(uuid4())
    content = resource.content
    if resource.resource_type == ResourceType.QUIZ:
        if resource.content_format != "json":
            raise ValueError("cached quiz must use JSON content")
        try:
            document = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("cached quiz contains invalid JSON") from error
        questions = document.get("questions") if isinstance(document, dict) else None
        if not isinstance(questions, list) or not questions:
            raise ValueError("cached quiz has no questions")
        local_ids: set[str] = set()
        for index, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                raise ValueError("cached quiz question is invalid")
            raw_id = str(question.get("id") or f"q{index}").strip()
            local_id = raw_id.partition("::")[2] or raw_id
            if not local_id or local_id in local_ids:
                raise ValueError("cached quiz question ids are invalid")
            local_ids.add(local_id)
            question["id"] = f"{new_resource_id}::{local_id}"
        content = json.dumps(document, ensure_ascii=False, indent=2)
    return resource.model_copy(
        deep=True,
        update={
            "resource_id": new_resource_id,
            "content": content,
            "review_status": "pending",
            "created_at": utc_now(),
        },
    )
