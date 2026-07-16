from __future__ import annotations

from fastapi import FastAPI


EXPECTED_OPERATIONS = {
    ("/api/health", "get"): {
        "request": None,
        "responses": {"200": "#/components/schemas/HealthResponse"},
    },
    ("/api/profile/chat", "post"): {
        "request": "#/components/schemas/ProfileChatRequest",
        "responses": {
            "200": "#/components/schemas/ProfileChatResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/profile/{student_id}", "get"): {
        "request": None,
        "responses": {
            "200": "#/components/schemas/StudentProfile",
            "404": "#/components/schemas/ErrorResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/path/generate", "post"): {
        "request": "#/components/schemas/PathGenerateRequest",
        "responses": {
            "200": "#/components/schemas/PathGenerateResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/resources/generate", "post"): {
        "request": "#/components/schemas/ResourceGenerationRequest",
        "responses": {
            "202": "#/components/schemas/TaskAcceptedResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/tasks/{task_id}", "get"): {
        "request": None,
        "responses": {
            "200": "#/components/schemas/TaskState",
            "404": "#/components/schemas/ErrorResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/tasks/{task_id}/events", "get"): {
        "request": None,
        "responses": {
            "200": None,
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
    ("/api/evaluation/submit", "post"): {
        "request": "#/components/schemas/EvaluationSubmission",
        "responses": {
            # Freeze the current route exactly: it returns JSONResponse without a
            # response_model, so the successful OpenAPI response has no schema.
            "200": None,
            "422": "#/components/schemas/HTTPValidationError",
            "501": "#/components/schemas/ErrorResponse",
        },
    },
    ("/api/resources/{resource_id}", "get"): {
        "request": None,
        "responses": {
            "200": "#/components/schemas/Resource",
            "404": "#/components/schemas/ErrorResponse",
            "422": "#/components/schemas/HTTPValidationError",
        },
    },
}


EXPECTED_PROPERTIES = {
    "ChatMessage": {"message_id", "role", "content"},
    "ProfileChatRequest": {
        "student_id",
        "conversation_id",
        "messages",
        "evaluation_summary",
    },
    "ProfileChatResponse": {
        "profile",
        "missing_dimensions",
        "next_question",
        "is_complete",
        "extraction_mode",
    },
    "StudentProfile": {
        "student_id",
        "version",
        "major",
        "course",
        "knowledge_level",
        "learning_goals",
        "weak_topics",
        "learning_history",
        "cognitive_style",
        "language_preference",
        "resource_preference",
        "time_budget",
        "evidence",
        "confidence",
        "updated_at",
    },
    "PathGenerateRequest": {
        "student_id",
        "profile",
        "previous_path_id",
        "evaluation_summary",
    },
    "PathGenerateResponse": {"path"},
    "LearningPath": {
        "path_id",
        "student_id",
        "profile_version",
        "course",
        "status",
        "steps",
        "adjustment_reason",
        "generation_mode",
        "created_at",
    },
    "LearningPathStep": {
        "step",
        "topic",
        "learning_goal",
        "reason",
        "recommended_resources",
        "completion_criteria",
        "estimated_minutes",
        "prerequisites",
    },
    "ResourceGenerationRequest": {
        "student_id",
        "path_id",
        "step",
        "resource_types",
        "regenerate",
    },
    "TaskAcceptedResponse": {"task_id", "status", "status_url", "events_url"},
    "TaskState": {
        "task_id",
        "task_type",
        "student_id",
        "status",
        "progress",
        "current_stage",
        "requested_resource_types",
        "result_resource_ids",
        "agent_runs",
        "errors",
        "created_at",
        "updated_at",
    },
    "Resource": {
        "resource_id",
        "resource_type",
        "title",
        "content",
        "content_format",
        "target_topic",
        "difficulty",
        "personalization_reason",
        "source_references",
        "review_status",
        "created_at",
    },
    "EvaluationSubmission": {
        "student_id",
        "path_id",
        "step",
        "answers",
        "time_spent_minutes",
    },
}


EXPECTED_REQUIRED = {
    "ChatMessage": {"role", "content"},
    "ProfileChatRequest": {"student_id", "messages"},
    "ProfileChatResponse": {
        "profile",
        "missing_dimensions",
        "next_question",
        "is_complete",
        "extraction_mode",
    },
    "StudentProfile": {
        "student_id",
        "version",
        "major",
        "course",
        "knowledge_level",
        "learning_goals",
        "weak_topics",
        "learning_history",
        "cognitive_style",
        "language_preference",
        "resource_preference",
        "time_budget",
        "confidence",
    },
    "PathGenerateRequest": {"student_id"},
    "PathGenerateResponse": {"path"},
    "LearningPath": {
        "path_id",
        "student_id",
        "profile_version",
        "course",
        "steps",
        "generation_mode",
    },
    "LearningPathStep": {
        "step",
        "topic",
        "learning_goal",
        "reason",
        "recommended_resources",
        "completion_criteria",
        "estimated_minutes",
    },
    "ResourceGenerationRequest": {"student_id", "path_id", "step"},
    "TaskAcceptedResponse": {"task_id", "status", "status_url", "events_url"},
    "TaskState": {"task_id", "task_type", "student_id", "current_stage"},
    "Resource": {
        "resource_id",
        "resource_type",
        "title",
        "content",
        "content_format",
        "target_topic",
        "difficulty",
        "personalization_reason",
        "source_references",
        "review_status",
    },
    "EvaluationSubmission": {
        "student_id",
        "path_id",
        "step",
        "answers",
        "time_spent_minutes",
    },
}


def _json_schema(operation: dict, status_code: str) -> dict:
    return (
        operation.get("responses", {})
        .get(status_code, {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )


def _request_ref(operation: dict) -> str | None:
    schema = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    return schema.get("$ref")


def test_current_openapi_operations_are_frozen(test_app: FastAPI) -> None:
    document = test_app.openapi()
    operations = {
        (path, method)
        for path, path_item in document["paths"].items()
        for method in path_item
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert operations == set(EXPECTED_OPERATIONS)

    for (path, method), expected in EXPECTED_OPERATIONS.items():
        operation = document["paths"][path][method]
        assert _request_ref(operation) == expected["request"]
        assert set(operation["responses"]) == set(expected["responses"])
        for status_code, expected_ref in expected["responses"].items():
            schema = _json_schema(operation, status_code)
            assert schema.get("$ref") == expected_ref
            if expected_ref is None:
                assert schema == {}


def test_current_public_schema_fields_are_frozen(test_app: FastAPI) -> None:
    schemas = test_app.openapi()["components"]["schemas"]
    for name, expected_properties in EXPECTED_PROPERTIES.items():
        schema = schemas[name]
        assert schema.get("additionalProperties") is False
        assert set(schema["properties"]) == expected_properties
        assert set(schema.get("required", [])) == EXPECTED_REQUIRED[name]

    # EvaluationResult exists as a Python schema but is intentionally absent
    # from today's OpenAPI because the evaluation route has no response_model.
    assert "EvaluationResult" not in schemas


def test_current_public_enums_are_frozen(test_app: FastAPI) -> None:
    schemas = test_app.openapi()["components"]["schemas"]
    assert schemas["Difficulty"]["enum"] == ["beginner", "intermediate", "advanced"]
    assert schemas["ResourceType"]["enum"] == [
        "explanation",
        "mind_map",
        "quiz",
        "reading",
        "coding",
    ]
    assert schemas["TaskStatus"]["enum"] == [
        "pending",
        "running",
        "completed",
        "partial_success",
        "failed",
    ]
    assert schemas["AgentRunStatus"]["enum"] == [
        "pending",
        "started",
        "completed",
        "failed",
        "skipped",
    ]
    assert schemas["ProfileChatResponse"]["properties"]["extraction_mode"]["enum"] == [
        "development_heuristic",
        "llm_structured",
    ]
    assert schemas["LearningPath"]["properties"]["generation_mode"]["enum"] == [
        "development_rule_based",
        "llm_structured",
    ]
    assert schemas["Resource"]["properties"]["content_format"]["enum"] == [
        "markdown",
        "mermaid",
        "json",
        "python",
        "text",
    ]
    assert schemas["Resource"]["properties"]["review_status"]["enum"] == [
        "pending",
        "approved",
        "rejected",
        "needs_revision",
    ]
