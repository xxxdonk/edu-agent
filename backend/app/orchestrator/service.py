from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from app.database import Repository
from app.schemas import Resource, ResourceGenerationRequest, ResourceType, TaskState, TaskStatus
from app.schemas.common import utc_now
from app.schemas.task import AgentRun, AgentRunStatus

from .contracts import AgentRegistry, SharedAgentContext


@dataclass(slots=True)
class _ExecutionResult:
    resource_type: ResourceType
    agent_name: str
    resource: Resource | None = None
    error: str | None = None


class Orchestrator:
    def __init__(self, repository: Repository, registry: AgentRegistry) -> None:
        self.repository = repository
        self.registry = registry

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
                        f"{result.agent_name} 已完成"
                        if result.resource
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
        reviewer_error: str | None = None
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
            review_results = await asyncio.gather(
                *(
                    self.registry.reviewer.review(result.resource, context)
                    for result in successful
                    if result.resource is not None
                ),
                return_exceptions=True,
            )
            for generated, review_result in zip(successful, review_results, strict=True):
                if isinstance(review_result, BaseException):
                    reviewer_error = str(review_result)
                    errors.append(f"review {generated.resource_type.value}: {reviewer_error}")
                    if generated.resource:
                        reviewed_resources.append(generated.resource)
                else:
                    # Reviewer 返回 (Resource, dict)，解包元组
                    if isinstance(review_result, tuple):
                        reviewed_resource, _review_meta = review_result
                    else:
                        reviewed_resource = review_result
                    reviewed_resources.append(Resource.model_validate(reviewed_resource))
            reviewer_run.status = (
                AgentRunStatus.FAILED if reviewer_error else AgentRunStatus.COMPLETED
            )
            reviewer_run.completed_at = utc_now()
            reviewer_run.error = reviewer_error
            self.repository.append_event(
                task.task_id,
                event_type="review",
                status="failed" if reviewer_error else "completed",
                progress=90,
                message="Reviewer Agent 审校失败" if reviewer_error else "Reviewer Agent 审校完成",
                agent=self.registry.reviewer.agent_name,
                error=reviewer_error,
            )
        elif successful:
            reviewer_error = "Reviewer Agent 尚未注册"
            errors.append(reviewer_error)
            reviewer_run.status = AgentRunStatus.SKIPPED
            reviewer_run.completed_at = utc_now()
            reviewer_run.error = reviewer_error
            reviewed_resources = [result.resource for result in successful if result.resource]
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
        if not successful:
            task.status = TaskStatus.FAILED
        elif errors:
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
            )
        except Exception as exc:
            return _ExecutionResult(
                resource_type=resource_type,
                agent_name=agent_name,
                error=str(exc),
            )
