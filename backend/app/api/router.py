from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field

from app.orchestrator import SharedAgentContext
from app.schemas import (
    ErrorResponse,
    EvaluationSubmission,
    LearningPath,
    PathGenerateRequest,
    PathGenerateResponse,
    ProfileChatRequest,
    ProfileChatResponse,
    Resource,
    ResourceGenerationRequest,
    StudentProfile,
    TaskAcceptedResponse,
    TaskState,
    TaskStatus,
)
from app.schemas.common import ApiModel, ErrorDetail

router = APIRouter(prefix="/api")


class HealthResponse(ApiModel):
    status: str
    service: str
    version: str
    environment: str
    database: str


def _not_found(entity: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": f"{entity.upper()}_NOT_FOUND",
            "message": f"{entity} not found: {identifier}",
            "details": {"id": identifier},
        },
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    database_ok = request.app.state.database.ping()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        service="edu-agent-api",
        version="0.1.0",
        environment=request.app.state.settings.environment,
        database="ok" if database_ok else "unavailable",
    )


@router.post(
    "/profile/chat",
    response_model=ProfileChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["profile"],
)
async def profile_chat(payload: ProfileChatRequest, request: Request) -> ProfileChatResponse:
    repository = request.app.state.repository
    previous = repository.get_latest_profile(payload.student_id)
    response = await request.app.state.profile_agent.extract(payload, previous)
    repository.save_profile(response.profile)
    return response


@router.get(
    "/profile/{student_id}",
    response_model=StudentProfile,
    responses={404: {"model": ErrorResponse}},
    tags=["profile"],
)
async def get_profile(student_id: str, request: Request) -> StudentProfile:
    profile = request.app.state.repository.get_latest_profile(student_id)
    if profile is None:
        raise _not_found("profile", student_id)
    return profile


@router.post(
    "/path/generate",
    response_model=PathGenerateResponse,
    tags=["learning-path"],
)
async def generate_path(payload: PathGenerateRequest, request: Request) -> PathGenerateResponse:
    repository = request.app.state.repository
    profile = payload.profile or repository.get_latest_profile(payload.student_id)
    if profile is None:
        raise _not_found("profile", payload.student_id)
    if profile.student_id != payload.student_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "STUDENT_ID_MISMATCH",
                "message": "payload.student_id must match profile.student_id",
                "details": {},
            },
        )
    previous_path = (
        repository.get_path(payload.previous_path_id)
        if payload.previous_path_id
        else None
    )
    path = await request.app.state.planner_agent.generate(
        profile,
        previous_path=previous_path,
        previous_path_id=payload.previous_path_id,
        evaluation_summary=payload.evaluation_summary,
    )
    repository.save_path(path)
    return PathGenerateResponse(path=path)


@router.post(
    "/resources/generate",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["resources"],
)
async def generate_resources(
    payload: ResourceGenerationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TaskAcceptedResponse:
    repository = request.app.state.repository
    profile = repository.get_latest_profile(payload.student_id)
    if profile is None:
        raise _not_found("profile", payload.student_id)
    path = repository.get_path(payload.path_id)
    if path is None:
        raise _not_found("path", payload.path_id)
    if path.student_id != payload.student_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PATH_OWNER_MISMATCH",
                "message": "path does not belong to student_id",
                "details": {},
            },
        )
    if payload.step not in {item.step for item in path.steps}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PATH_STEP_NOT_FOUND",
                "message": f"step {payload.step} does not exist in path",
                "details": {},
            },
        )

    task = request.app.state.orchestrator.create_resource_task(payload)
    context = SharedAgentContext(
        task_id=task.task_id,
        request=payload,
        profile=profile,
        path=path,
    )
    background_tasks.add_task(request.app.state.orchestrator.run_resource_task, context)
    return TaskAcceptedResponse(
        task_id=task.task_id,
        status=task.status,
        status_url=f"/api/tasks/{task.task_id}",
        events_url=f"/api/tasks/{task.task_id}/events",
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskState,
    responses={404: {"model": ErrorResponse}},
    tags=["tasks"],
)
async def get_task(task_id: str, request: Request) -> TaskState:
    task = request.app.state.repository.get_task(task_id)
    if task is None:
        raise _not_found("task", task_id)
    return task


@router.get("/tasks/{task_id}/events", tags=["tasks"])
async def task_events(
    task_id: str,
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    repository = request.app.state.repository
    if repository.get_task(task_id) is None:
        raise _not_found("task", task_id)
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def event_stream():
        nonlocal cursor
        last_emit = time.monotonic()
        terminal = {
            TaskStatus.COMPLETED,
            TaskStatus.PARTIAL_SUCCESS,
            TaskStatus.FAILED,
        }
        while True:
            if await request.is_disconnected():
                break
            events = repository.list_events(task_id, cursor)
            for event in events:
                cursor = event.sequence
                payload = event.model_dump(mode="json")
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
                last_emit = time.monotonic()
            task = repository.get_task(task_id)
            if task and task.status in terminal and not repository.list_events(task_id, cursor):
                break
            if time.monotonic() - last_emit >= 15:
                yield ": heartbeat\n\n"
                last_emit = time.monotonic()
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/evaluation/submit",
    responses={501: {"model": ErrorResponse}},
    tags=["evaluation"],
)
async def submit_evaluation(payload: EvaluationSubmission, request: Request) -> JSONResponse:
    try:
        from app.evaluation import EvaluationAgent

        evaluator = EvaluationAgent()
        result = await evaluator.evaluate(payload)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result.model_dump(mode="json"),
        )
    except Exception:
        body = ErrorResponse(
            error=ErrorDetail(
                code="EVALUATION_ERROR",
                message="Evaluation failed.",
                details={"mock": True},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=body.model_dump(),
        )


@router.get(
    "/resources/{resource_id}",
    response_model=Resource,
    responses={404: {"model": ErrorResponse}},
    tags=["resources"],
)
async def get_resource(resource_id: str, request: Request) -> Resource:
    resource = request.app.state.repository.get_resource(resource_id)
    if resource is None:
        raise _not_found("resource", resource_id)
    return resource
