from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import uuid4

from app.database import Repository
from app.schemas import Resource, ResourceGenerationRequest, ResourceType, TaskState, TaskStatus
from app.schemas.common import utc_now
from app.schemas.task import AgentRun, AgentRunStatus

from .cache import (
    ResourceCache,
    ResourceCacheKey,
    clone_cached_resource,
    is_cacheable_resource,
)
from .contracts import AgentRegistry, SharedAgentContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ExecutionResult:
    resource_type: ResourceType
    agent_name: str
    resource: Resource | None = None
    error: str | None = None
    cache_key: ResourceCacheKey | None = None
    cache_hit: bool = False


class Orchestrator:
    def __init__(
        self,
        repository: Repository,
        registry: AgentRegistry,
        *,
        resource_cache: ResourceCache | None = None,
        model_identity: str = "unconfigured:<none>",
        knowledge_base_version: str = "unversioned",
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.resource_cache = resource_cache or ResourceCache(enabled=False)
        self.model_identity = model_identity
        self.knowledge_base_version = knowledge_base_version

    def create_resource_task(self, request: ResourceGenerationRequest) -> TaskState:
        task = TaskState(
            task_id=str(uuid4()),
            task_type="resource_generation",
            student_id=request.student_id,
            status=TaskStatus.PENDING,
            progress=0,
            current_stage="queued",
            requested_resource_types=request.resource_types,
            agent_runs=[
                AgentRun(
                    agent=f"{resource_type.value}_agent",
                    resource_type=resource_type,
                )
                for resource_type in request.resource_types
            ]
            + [AgentRun(agent="reviewer_agent")],
        )
        self.repository.save_task(task)
        self.repository.append_event(
            task.task_id,
            event_type="task",
            status="pending",
            progress=0,
            message="资源生成任务已进入队列",
        )
        return task

    async def run_resource_task(self, context: SharedAgentContext) -> None:
        """Run one task and always converge persisted state to a terminal status."""

        try:
            await self._run_resource_task(context)
        except Exception as exc:
            task = self.repository.get_task(context.task_id)
            if task is None:
                return
            safe_error = f"orchestrator_internal_error:{type(exc).__name__}"
            task.status = TaskStatus.FAILED
            task.progress = 100
            task.current_stage = "failed"
            task.errors = [*task.errors, safe_error]
            task.updated_at = utc_now()
            for run in task.agent_runs:
                if run.status == AgentRunStatus.STARTED:
                    run.status = AgentRunStatus.FAILED
                    run.completed_at = task.updated_at
                    run.error = safe_error
            try:
                self.repository.save_task(task)
                self.repository.append_event(
                    task.task_id,
                    event_type="task",
                    status=TaskStatus.FAILED.value,
                    progress=100,
                    message="资源生成任务因内部错误终止",
                    agent="orchestrator_agent",
                    error=safe_error,
                )
            except Exception:
                # The persistence layer itself failed; there is no safer state
                # mutation available in this single-process demo runtime.
                return

    async def _run_resource_task(self, context: SharedAgentContext) -> None:
        task = self.repository.get_task(context.task_id)
        if task is None:
            return
        task.status = TaskStatus.RUNNING
        task.progress = 10
        task.current_stage = "generating_resources"
        task.updated_at = utc_now()
        for run in task.agent_runs[:-1]:
            run.status = AgentRunStatus.STARTED
            run.started_at = task.updated_at
        self.repository.save_task(task)
        self.repository.append_event(
            task.task_id,
            event_type="task",
            status="started",
            progress=10,
            message="Orchestrator 已启动并行资源生成",
            agent="orchestrator_agent",
        )

        completed_count = 0
        completion_lock = asyncio.Lock()
        total = len(context.request.resource_types)

        async def execute(resource_type: ResourceType) -> _ExecutionResult:
            nonlocal completed_count
            result = await self._execute_resource(resource_type, context)
            async with completion_lock:
                completed_count += 1
                progress = 10 + int(60 * completed_count / max(total, 1))
                self.repository.append_event(
                    task.task_id,
                    event_type="agent",
                    status="completed" if result.resource else "failed",
                    progress=progress,
                    message=(
                        f"{result.agent_name} 已完成 cache_hit={str(result.cache_hit).lower()}"
                        if result.resource is not None
                        else f"{result.agent_name} 执行失败"
                    ),
                    agent=result.agent_name,
                    resource_type=resource_type,
                    error=result.error,
                )
            return result

        results = await asyncio.gather(
            *(execute(resource_type) for resource_type in context.request.resource_types),
            return_exceptions=False,
        )
        successful = [result for result in results if result.resource is not None]
        errors = [result.error for result in results if result.error]

        reviewed_resources: list[Resource] = []
        reviewer_failures: list[str] = []
        reviewer_run = task.agent_runs[-1]
        if successful and self.registry.reviewer:
            reviewer_run.status = AgentRunStatus.STARTED
            reviewer_run.started_at = utc_now()
            self.repository.append_event(
                task.task_id,
                event_type="review",
                status="started",
                progress=75,
                message="资源生成完毕，Reviewer Agent 开始统一审校",
                agent=self.registry.reviewer.agent_name,
            )

            review_count = 0
            review_lock = asyncio.Lock()

            async def review_one(generated: _ExecutionResult) -> Resource:
                nonlocal review_count
                assert generated.resource is not None
                self.repository.append_event(
                    task.task_id,
                    event_type="review",
                    status="started",
                    progress=75,
                    message=f"Reviewer Agent 开始审校 {generated.resource_type.value}",
                    agent=self.registry.reviewer.agent_name,
                    resource_type=generated.resource_type,
                )
                try:
                    reviewed = Resource.model_validate(
                        await self.registry.reviewer.review(generated.resource, context)
                    )
                except Exception as exc:
                    safe_error = f"review_error:{type(exc).__name__}"
                    self.repository.append_event(
                        task.task_id,
                        event_type="review",
                        status="failed",
                        progress=75,
                        message=f"Reviewer Agent 审校 {generated.resource_type.value} 失败",
                        agent=self.registry.reviewer.agent_name,
                        resource_type=generated.resource_type,
                        error=safe_error,
                    )
                    raise

                async with review_lock:
                    review_count += 1
                    progress = 75 + int(15 * review_count / max(len(successful), 1))
                    accepted = reviewed.review_status in {"approved", "needs_revision"}
                    self.repository.append_event(
                        task.task_id,
                        event_type="review",
                        status="completed" if accepted else "failed",
                        progress=progress,
                        message=(
                            f"Reviewer Agent 已审校 {generated.resource_type.value}："
                            f"{reviewed.review_status}"
                        ),
                        agent=self.registry.reviewer.agent_name,
                        resource_type=generated.resource_type,
                        error=(
                            None
                            if accepted
                            else f"review_status={reviewed.review_status}"
                        ),
                    )
                return reviewed

            review_results = await asyncio.gather(
                *(review_one(result) for result in successful),
                return_exceptions=True,
            )
            for generated, review_result in zip(successful, review_results, strict=True):
                if isinstance(review_result, BaseException):
                    failure = (
                        f"review {generated.resource_type.value}:"
                        f"{type(review_result).__name__}"
                    )
                    reviewer_failures.append(failure)
                    errors.append(failure)
                else:
                    reviewed_resource = Resource.model_validate(review_result)
                    if reviewed_resource.review_status == "approved":
                        reviewed_resources.append(reviewed_resource)
                        self._store_approved_resource(
                            generated,
                            reviewed_resource,
                            task_id=task.task_id,
                        )
                    elif reviewed_resource.review_status == "needs_revision":
                        reviewed_resources.append(reviewed_resource)
                        errors.append(
                            f"review {generated.resource_type.value}:needs_revision"
                        )
                    else:
                        errors.append(
                            f"review {generated.resource_type.value}:"
                            f"{reviewed_resource.review_status}"
                        )
            reviewer_run.status = (
                AgentRunStatus.FAILED if reviewer_failures else AgentRunStatus.COMPLETED
            )
            reviewer_run.completed_at = utc_now()
            reviewer_run.error = "; ".join(reviewer_failures) or None
            self.repository.append_event(
                task.task_id,
                event_type="review",
                status="failed" if reviewer_failures else "completed",
                progress=90,
                message=(
                    "Reviewer Agent 存在执行失败"
                    if reviewer_failures
                    else "Reviewer Agent 已完成全部审校"
                ),
                agent=self.registry.reviewer.agent_name,
                error=reviewer_run.error,
            )
        elif successful:
            reviewer_error = "Reviewer Agent 尚未注册"
            errors.append(reviewer_error)
            reviewer_run.status = AgentRunStatus.SKIPPED
            reviewer_run.completed_at = utc_now()
            reviewer_run.error = reviewer_error
            self.repository.append_event(
                task.task_id,
                event_type="review",
                status="skipped",
                progress=90,
                message=reviewer_error,
                agent="reviewer_agent",
                error=reviewer_error,
            )
        else:
            reviewer_run.status = AgentRunStatus.SKIPPED
            reviewer_run.completed_at = utc_now()
            reviewer_run.error = "没有可审校的成功资源"

        for resource in reviewed_resources:
            self.repository.save_resource(resource, task.task_id)

        result_by_type = {result.resource_type: result for result in results}
        for run in task.agent_runs[:-1]:
            result = result_by_type[run.resource_type]
            run.completed_at = utc_now()
            run.status = AgentRunStatus.COMPLETED if result.resource else AgentRunStatus.FAILED
            run.agent = result.agent_name
            run.error = result.error

        task.result_resource_ids = [resource.resource_id for resource in reviewed_resources]
        task.errors = [error for error in errors if error]
        task.progress = 100
        task.current_stage = "finished"
        if not reviewed_resources:
            task.status = TaskStatus.FAILED
        elif errors or len(reviewed_resources) < len(context.request.resource_types):
            task.status = TaskStatus.PARTIAL_SUCCESS
        else:
            task.status = TaskStatus.COMPLETED
        task.updated_at = utc_now()
        self.repository.save_task(task)
        self.repository.append_event(
            task.task_id,
            event_type="task",
            status=task.status.value,
            progress=100,
            message=f"任务结束：成功生成 {len(reviewed_resources)} 项资源",
            agent="orchestrator_agent",
            error="; ".join(task.errors) if task.errors else None,
        )

    async def _execute_resource(
        self,
        resource_type: ResourceType,
        context: SharedAgentContext,
    ) -> _ExecutionResult:
        agent = self.registry.resource_agent(resource_type)
        agent_name = agent.agent_name if agent else f"{resource_type.value}_agent"
        self.repository.append_event(
            context.task_id,
            event_type="agent",
            status="started",
            progress=10,
            message=f"{agent_name} 开始生成",
            agent=agent_name,
            resource_type=resource_type,
        )
        if agent is None:
            return _ExecutionResult(
                resource_type=resource_type,
                agent_name=agent_name,
                error=f"{resource_type.value} Agent 尚未注册（第一阶段接口桩）",
            )

        cache_key = self._cache_key(context, resource_type)
        if cache_key is not None:
            if context.request.regenerate:
                self.resource_cache.invalidate(cache_key)
                logger.info(
                    "resource_cache_bypass task_id=%s resource_type=%s key=%s",
                    context.task_id,
                    resource_type.value,
                    cache_key.digest[:12],
                )
            else:
                cached_resource = self.resource_cache.get(cache_key)
                if cached_resource is not None:
                    try:
                        cloned_resource = Resource.model_validate(
                            clone_cached_resource(cached_resource)
                        )
                        if cloned_resource.resource_type != resource_type:
                            raise ValueError("cached resource_type mismatch")
                    except Exception as error:
                        self.resource_cache.invalidate(cache_key)
                        logger.warning(
                            "resource_cache_invalid task_id=%s resource_type=%s "
                            "key=%s error=%s",
                            context.task_id,
                            resource_type.value,
                            cache_key.digest[:12],
                            type(error).__name__,
                        )
                    else:
                        self._emit_cache_hit_retrieval_events(
                            context,
                            resource_type,
                            cache_key,
                        )
                        logger.info(
                            "resource_cache_hit task_id=%s resource_type=%s key=%s",
                            context.task_id,
                            resource_type.value,
                            cache_key.digest[:12],
                        )
                        return _ExecutionResult(
                            resource_type=resource_type,
                            agent_name=agent_name,
                            resource=cloned_resource,
                            cache_key=cache_key,
                            cache_hit=True,
                        )
        try:
            resource = Resource.model_validate(await agent.generate(context))
            if resource.resource_type != resource_type:
                raise ValueError(
                    f"resource_type mismatch: expected {resource_type.value}, "
                    f"got {resource.resource_type.value}"
                )
            return _ExecutionResult(
                resource_type=resource_type,
                agent_name=agent_name,
                resource=resource,
                cache_key=cache_key,
            )
        except Exception as exc:
            return _ExecutionResult(
                resource_type=resource_type,
                agent_name=agent_name,
                error=str(exc),
                cache_key=cache_key,
            )

    def _cache_key(
        self,
        context: SharedAgentContext,
        resource_type: ResourceType,
    ) -> ResourceCacheKey | None:
        if not self.resource_cache.enabled:
            return None
        try:
            return ResourceCacheKey.from_context(
                context,
                resource_type,
                model_identity=self.model_identity,
                knowledge_base_version=self.knowledge_base_version,
            )
        except Exception as error:
            logger.warning(
                "resource_cache_key_failed task_id=%s resource_type=%s error=%s",
                context.task_id,
                resource_type.value,
                type(error).__name__,
            )
            return None

    def _store_approved_resource(
        self,
        generated: _ExecutionResult,
        resource: Resource,
        *,
        task_id: str,
    ) -> None:
        if generated.cache_key is None or not is_cacheable_resource(resource):
            return
        try:
            self.resource_cache.put(generated.cache_key, resource)
        except Exception as error:
            logger.warning(
                "resource_cache_write_failed task_id=%s resource_type=%s "
                "key=%s error=%s",
                task_id,
                generated.resource_type.value,
                generated.cache_key.digest[:12],
                type(error).__name__,
            )

    def _emit_cache_hit_retrieval_events(
        self,
        context: SharedAgentContext,
        resource_type: ResourceType,
        cache_key: ResourceCacheKey,
    ) -> None:
        self.repository.append_event(
            context.task_id,
            event_type="agent",
            status="started",
            progress=10,
            message="Retriever Agent 开始读取已验证的知识库缓存快照",
            agent="retriever_agent",
            resource_type=resource_type,
        )
        self.repository.append_event(
            context.task_id,
            event_type="agent",
            status="completed",
            progress=15,
            message=(
                "Retriever Agent 已复用相同知识库版本的审校资源 "
                f"cache_hit=true key={cache_key.digest[:12]}"
            ),
            agent="retriever_agent",
            resource_type=resource_type,
        )
