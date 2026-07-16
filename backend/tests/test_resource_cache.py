from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from app.database import Repository, SQLiteDatabase
from app.orchestrator import AgentRegistry, Orchestrator, ResourceCache, SharedAgentContext
from app.orchestrator.cache import (
    ResourceCacheKey,
    clone_cached_resource,
    is_cacheable_resource,
)
from app.planner import DevelopmentPlannerAgent, PlannerAgent
from app.profile import DevelopmentProfileAgent, ProfileAgent
from app.rag.retriever import knowledge_base_version
from app.schemas import (
    ProfileChatRequest,
    Resource,
    ResourceGenerationRequest,
    ResourceType,
    SourceReference,
)
from app.schemas.common import Difficulty
from app.schemas.profile import ChatMessage


def _context(
    *,
    resource_types: list[ResourceType] | None = None,
    regenerate: bool = False,
) -> SharedAgentContext:
    profile_request = ProfileChatRequest(
        student_id="cache-test-student",
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "我是人工智能专业学生，刚开始学习机器学习，梯度下降一直没弄懂。"
                    "我希望完成分类项目，喜欢图示和代码案例，每天学习45分钟。"
                ),
            )
        ],
    )
    profile = DevelopmentProfileAgent().extract(profile_request, None).profile
    path = DevelopmentPlannerAgent().generate(profile)
    request = ResourceGenerationRequest(
        student_id=profile.student_id,
        path_id=path.path_id,
        step=1,
        resource_types=resource_types or [ResourceType.QUIZ],
        regenerate=regenerate,
    )
    return SharedAgentContext(
        task_id="placeholder-task",
        request=request,
        profile=profile,
        path=path,
    )


def _resource(
    context: SharedAgentContext,
    resource_type: ResourceType,
) -> Resource:
    resource_id = str(uuid4())
    topic = next(
        step.topic for step in context.path.steps if step.step == context.request.step
    )
    if resource_type == ResourceType.QUIZ:
        content = json.dumps(
            {
                "topic": topic,
                "questions": [
                    {
                        "id": f"{resource_id}::q1",
                        "type": "single_choice",
                        "level": "basic",
                        "question": "目标函数的作用是什么？",
                        "options": ["A. 衡量预测误差", "B. 删除数据"],
                        "answer": "A",
                        "explanation": "目标函数用于量化模型预测与真实结果之间的差异。",
                    }
                ],
            },
            ensure_ascii=False,
        )
        content_format = "json"
    else:
        content = (
            f"# {topic}\n\n这是与{topic}相关的个性化课程资源，包含原理、步骤、"
            "验证方法和分类项目中的应用示例。"
        )
        content_format = {
            ResourceType.EXPLANATION: "markdown",
            ResourceType.MIND_MAP: "mermaid",
            ResourceType.READING: "markdown",
            ResourceType.CODING: "python",
        }[resource_type]
    return Resource(
        resource_id=resource_id,
        resource_type=resource_type,
        title=f"{topic} 学习资源",
        content=content,
        content_format=content_format,
        target_topic=topic,
        difficulty=context.profile.knowledge_level.value or Difficulty.BEGINNER,
        personalization_reason="针对梯度下降薄弱点、图示偏好和分类项目目标生成。",
        source_references=[
            SourceReference(
                source_id="ml-chapter-02",
                title="线性回归",
                locator="data/machine_learning/02-线性回归.md#梯度下降",
                chunk_id="chapter-02-chunk-001",
            )
        ],
        review_status="pending",
    )


class _CountingAgent:
    def __init__(
        self,
        resource_type: ResourceType,
        *,
        barrier: "_ConcurrencyBarrier | None" = None,
    ) -> None:
        self.resource_type = resource_type
        self.agent_name = f"counting_{resource_type.value}_agent"
        self.calls = 0
        self._barrier = barrier

    async def generate(self, context: SharedAgentContext) -> Resource:
        self.calls += 1
        if self._barrier is not None:
            await self._barrier.wait()
        return _resource(context, self.resource_type)


class _CountingReviewer:
    agent_name = "counting_reviewer_agent"

    def __init__(self) -> None:
        self.calls = 0

    async def review(
        self,
        resource: Resource,
        context: SharedAgentContext,
    ) -> Resource:
        self.calls += 1
        return resource.model_copy(update={"review_status": "approved"})


class _ConcurrencyBarrier:
    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.active = 0
        self.peak = 0
        self._lock = asyncio.Lock()
        self._all_started = asyncio.Event()

    async def wait(self) -> None:
        async with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == self.expected:
                self._all_started.set()
        try:
            await asyncio.wait_for(self._all_started.wait(), timeout=1.0)
        finally:
            async with self._lock:
                self.active -= 1


def _repository(tmp_path: Path) -> Repository:
    database = SQLiteDatabase(tmp_path / "cache-test.db")
    database.initialize()
    return Repository(database)


async def _run_task(
    orchestrator: Orchestrator,
    context: SharedAgentContext,
) -> str:
    task = orchestrator.create_resource_task(context.request)
    await orchestrator.run_resource_task(
        replace(context, task_id=task.task_id)
    )
    return task.task_id


def test_cache_hit_rebinds_quiz_and_still_runs_reviewer(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    registry = AgentRegistry()
    agent = _CountingAgent(ResourceType.QUIZ)
    reviewer = _CountingReviewer()
    registry.register_resource(agent)
    registry.register_reviewer(reviewer)
    cache = ResourceCache(enabled=True, ttl_seconds=60, max_entries=8)
    orchestrator = Orchestrator(
        repository,
        registry,
        resource_cache=cache,
        model_identity="openai_compatible:test-model",
        knowledge_base_version="kb-test-sha",
    )
    context = _context()

    first_task_id = asyncio.run(_run_task(orchestrator, context))
    second_task_id = asyncio.run(_run_task(orchestrator, context))

    first_task = repository.get_task(first_task_id)
    second_task = repository.get_task(second_task_id)
    assert first_task is not None and second_task is not None
    assert first_task.status.value == second_task.status.value == "completed"
    assert agent.calls == 1
    assert reviewer.calls == 2
    first_resource = repository.get_resource(first_task.result_resource_ids[0])
    second_resource = repository.get_resource(second_task.result_resource_ids[0])
    assert first_resource is not None and second_resource is not None
    assert first_resource.resource_id != second_resource.resource_id
    second_question = json.loads(second_resource.content)["questions"][0]
    assert second_question["id"].startswith(f"{second_resource.resource_id}::")
    assert second_resource.review_status == "approved"
    assert any(
        "cache_hit=true" in event.message
        for event in repository.list_events(second_task_id)
    )
    assert cache.stats.hits == 1

    regenerated_context = replace(
        context,
        request=context.request.model_copy(update={"regenerate": True}),
    )
    asyncio.run(_run_task(orchestrator, regenerated_context))
    assert agent.calls == 2
    assert reviewer.calls == 3
    assert cache.stats.invalidations == 1


def test_only_approved_non_fallback_resources_are_cacheable() -> None:
    context = _context()
    approved = _resource(context, ResourceType.EXPLANATION).model_copy(
        update={"review_status": "approved"}
    )

    assert is_cacheable_resource(approved)
    assert not is_cacheable_resource(
        approved.model_copy(update={"review_status": "needs_revision"})
    )
    assert not is_cacheable_resource(
        approved.model_copy(
            update={
                "personalization_reason": (
                    "development fallback: local template; "
                    + approved.personalization_reason
                )
            }
        )
    )


def test_development_fallback_is_never_reused_from_cache(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    registry = AgentRegistry()
    agent = _CountingAgent(ResourceType.EXPLANATION)
    reviewer = _CountingReviewer()

    async def generate_fallback(context: SharedAgentContext) -> Resource:
        agent.calls += 1
        return _resource(context, ResourceType.EXPLANATION).model_copy(
            update={
                "personalization_reason": (
                    "development fallback: local template; 针对梯度下降薄弱点。"
                )
            }
        )

    agent.generate = generate_fallback  # type: ignore[method-assign]
    registry.register_resource(agent)
    registry.register_reviewer(reviewer)
    cache = ResourceCache(enabled=True, ttl_seconds=60, max_entries=8)
    orchestrator = Orchestrator(
        repository,
        registry,
        resource_cache=cache,
        model_identity="openai_compatible:test-model",
        knowledge_base_version="kb-test-sha",
    )
    context = _context(resource_types=[ResourceType.EXPLANATION])

    asyncio.run(_run_task(orchestrator, context))
    asyncio.run(_run_task(orchestrator, context))

    assert agent.calls == 2
    assert reviewer.calls == 2
    assert cache.stats.entries == 0
    assert cache.stats.hits == 0


def test_cache_key_covers_every_invalidation_dimension() -> None:
    context = _context()
    key = ResourceCacheKey.from_context(
        context,
        ResourceType.QUIZ,
        model_identity="openai_compatible:model-a",
        knowledge_base_version="kb-a",
    )
    changed_step = context.path.steps[0].model_copy(
        update={"topic": context.path.steps[0].topic + "进阶"}
    )
    changed_path = context.path.model_copy(
        update={"steps": [changed_step, *context.path.steps[1:]]}
    )
    changed_context = replace(context, path=changed_path)
    variants = {
        replace(key, student_id="another-student").digest,
        replace(key, profile_version=key.profile_version + 1).digest,
        replace(key, path_id="another-path").digest,
        replace(key, step=key.step + 1).digest,
        ResourceCacheKey.from_context(
            changed_context,
            ResourceType.QUIZ,
            model_identity=key.model_identity,
            knowledge_base_version=key.knowledge_base_version,
        ).digest,
        replace(key, resource_type=ResourceType.READING).digest,
        replace(key, model_identity="openai_compatible:model-b").digest,
        replace(key, knowledge_base_version="kb-b").digest,
        replace(key, generator_revision="quiz-phase5-v2").digest,
    }

    assert key.student_id == context.request.student_id
    assert key.profile_version == context.profile.version
    assert key.path_id == context.path.path_id
    assert key.step == context.request.step
    assert key.model_identity == "openai_compatible:model-a"
    assert key.knowledge_base_version == "kb-a"
    assert len(variants) == 9
    assert key.digest not in variants


def test_cache_is_bounded_and_expires_entries() -> None:
    now = [0.0]
    cache = ResourceCache(
        enabled=True,
        ttl_seconds=10,
        max_entries=1,
        clock=lambda: now[0],
    )
    context = _context()
    resource = _resource(context, ResourceType.EXPLANATION).model_copy(
        update={"review_status": "approved"}
    )
    first_key = ResourceCacheKey.from_context(
        context,
        ResourceType.EXPLANATION,
        model_identity="provider:model",
        knowledge_base_version="kb",
    )
    second_key = replace(first_key, path_id="second-path")

    cache.put(first_key, resource)
    assert cache.get(first_key) is not None
    cache.put(second_key, resource)
    assert cache.get(first_key) is None
    now[0] = 11.0
    assert cache.get(second_key) is None

    stats = cache.stats
    assert stats.hits == 1
    assert stats.misses == 2
    assert stats.writes == 2
    assert stats.evictions == 1
    assert stats.expirations == 1
    assert stats.entries == 0


def test_clone_cached_resource_returns_a_deep_copy() -> None:
    context = _context()
    resource = _resource(context, ResourceType.QUIZ).model_copy(
        update={"review_status": "approved"}
    )

    cloned = clone_cached_resource(resource)

    assert cloned.resource_id != resource.resource_id
    assert cloned.review_status == "pending"
    assert json.loads(cloned.content)["questions"][0]["id"].startswith(
        f"{cloned.resource_id}::"
    )
    assert json.loads(resource.content)["questions"][0]["id"].startswith(
        f"{resource.resource_id}::"
    )


def test_knowledge_base_version_changes_with_loaded_file_content(
    tmp_path: Path,
) -> None:
    (tmp_path / "syllabus.md").write_text("# 课程\n第一版", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("不参与知识库", encoding="utf-8")
    first = knowledge_base_version(tmp_path)

    (tmp_path / "ignored.txt").write_text("仍然不参与", encoding="utf-8")
    assert knowledge_base_version(tmp_path) == first
    (tmp_path / "syllabus.md").write_text("# 课程\n第二版", encoding="utf-8")
    assert knowledge_base_version(tmp_path) != first


def test_five_resource_agents_enter_generation_concurrently(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    registry = AgentRegistry()
    resource_types = list(ResourceType)
    barrier = _ConcurrencyBarrier(len(resource_types))
    agents = [
        _CountingAgent(resource_type, barrier=barrier)
        for resource_type in resource_types
    ]
    for agent in agents:
        registry.register_resource(agent)
    reviewer = _CountingReviewer()
    registry.register_reviewer(reviewer)
    orchestrator = Orchestrator(
        repository,
        registry,
        resource_cache=ResourceCache(enabled=False),
    )
    context = _context(resource_types=resource_types)

    task_id = asyncio.run(_run_task(orchestrator, context))

    task = repository.get_task(task_id)
    assert task is not None
    assert task.status.value == "completed"
    assert barrier.peak == len(resource_types)
    assert reviewer.calls == len(resource_types)


def test_private_prompt_payloads_are_compact_but_keep_new_evidence() -> None:
    context = _context()
    evaluation_summary = "来源=evaluation；掌握度40%；薄弱点=梯度下降"
    profile_request = ProfileChatRequest(
        student_id=context.profile.student_id,
        messages=[
            ChatMessage(
                role="assistant",
                content="该评价摘要不是学生原话。",
            )
        ],
        evaluation_summary=evaluation_summary,
    )

    profile_payload = json.loads(
        ProfileAgent._prompt_payload(profile_request, context.profile)
    )
    compact_profile = profile_payload["previous_profile"]
    assert profile_payload["evaluation_summary"] == evaluation_summary
    assert profile_payload["messages"][0]["content"] == "该评价摘要不是学生原话。"
    assert "updated_at" not in compact_profile
    assert "evidence" not in compact_profile
    assert {"value", "confidence", "evidence_sources"} <= set(
        compact_profile["weak_topics"]
    )

    planner_payload = json.loads(
        PlannerAgent._prompt_payload(
            context.profile,
            context.path,
            evaluation_summary,
            ["梯度下降"],
        )
    )
    assert planner_payload["evaluation_summary"] == evaluation_summary
    assert planner_payload["target_topics"] == ["梯度下降"]
    assert planner_payload["constraints"]["max_minutes_per_step"] == 45
    assert planner_payload["constraints"]["priority_topics"] == ["梯度下降"]
    assert "updated_at" not in planner_payload["profile"]
    assert "created_at" not in planner_payload["previous_path"]
    assert planner_payload["previous_path"]["steps"][0]["topic"]
