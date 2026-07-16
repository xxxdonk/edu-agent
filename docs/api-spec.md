# EduAgent API 契约

版本：`api-contract-v0.1`

服务版本：`0.1.0`

Base URL：`http://127.0.0.1:8000`

OpenAPI：`/openapi.json`

Swagger UI：`/docs`

本文件描述当前实现。公共 API 共 9 个操作，路径、公共 Schema、字段和枚举均已冻结。除 SSE 外，请求与响应使用 JSON；时间为带时区的 ISO 8601 字符串。公共模型默认拒绝未知字段。

## 1. 公共枚举与实体

- `Difficulty`：`beginner | intermediate | advanced`
- `ResourceType`：`explanation | mind_map | quiz | reading | coding`
- `ReviewStatus`：`pending | approved | rejected | needs_revision`
- `TaskStatus`：`pending | running | completed | partial_success | failed`
- `AgentRunStatus`：`pending | started | completed | failed | skipped`

公共资源实体只能使用 `Resource`，异步任务实体只能使用 `TaskState`。

### StudentProfile

画像包含：

- `student_id`、`version`、`confidence`、`updated_at`
- `major`、`course`、`knowledge_level`
- `learning_goals`、`weak_topics`、`learning_history`
- `cognitive_style`、`language_preference`、`resource_preference`
- `time_budget`
- 顶层 `evidence`

每个画像维度是 `ProfileField`，包含 `value`、`evidence` 和 `confidence`。证据来源为 `conversation | evaluation | inference | system_default`。Evaluation 产生的事实必须标记为 `evaluation`，不能伪装成学生原话。

### LearningPath

路径包含 `path_id`、`student_id`、`profile_version`、`course`、`status`、`steps`、`adjustment_reason`、`generation_mode` 和 `created_at`。

每个步骤固定包含：

- `step`
- `topic`
- `learning_goal`
- `reason`
- `recommended_resources`
- `completion_criteria`
- `estimated_minutes`
- `prerequisites`

`generation_mode` 为 `llm_structured | development_rule_based`。

### Resource

```json
{
  "resource_id": "resource-id",
  "resource_type": "explanation",
  "title": "梯度下降课程讲解",
  "content": "# 梯度下降",
  "content_format": "markdown",
  "target_topic": "梯度下降",
  "difficulty": "beginner",
  "personalization_reason": "学生薄弱点包含梯度下降，偏好代码案例和图示。",
  "source_references": [
    {
      "source_id": "ml-chapter-02",
      "title": "线性回归",
      "locator": "data/machine_learning/02-线性回归.md#知识正文",
      "chunk_id": "chapter-02-chunk-003"
    }
  ],
  "review_status": "approved",
  "created_at": "2026-07-16T08:00:00Z"
}
```

`source_references` 至少一项，必须来自真实课程知识库。五类资源及推荐格式：

| `resource_type` | 内容 | `content_format` |
|---|---|---|
| `explanation` | Markdown 讲解 | `markdown` |
| `mind_map` | Mermaid mindmap 正文 | `mermaid` |
| `quiz` | 固定三层练习及答案 | `json` |
| `reading` | 拓展阅读 | `markdown` |
| `coding` | Python 实践 | `python` 或 `markdown` |

### TaskState 与 TaskEvent

`TaskState` 包含：

`task_id`、`task_type`、`student_id`、`status`、`progress`、`current_stage`、`requested_resource_types`、`result_resource_ids`、`agent_runs`、`errors`、`created_at`、`updated_at`。

SSE 中的 `TaskEvent` 包含：

`event_id`、`task_id`、`sequence`、`event_type`、`status`、`progress`、`message`、`agent`、`resource_type`、`error`、`created_at`。

### EvaluationSubmission 与 EvaluationResult

提交字段：

- `student_id`
- `path_id`
- `step`
- `answers[{question_id,response}]`
- `time_spent_minutes`

结果字段：

- `evaluation_id`
- `student_id`
- `path_id`
- `step`
- `mastery_score`
- `passed`
- `weak_topics`
- `feedback`
- `profile_update_required`
- `path_update_required`
- `evaluated_at`
- `profile_update_suggestions`
- `path_update_suggestions`

建议对象中包含已保存的画像版本、证据来源、新路径 ID、更新后路径和生成模式，前端直接采用后端已经持久化的结果。

## 2. API 清单

| 方法 | 路径 | 成功状态 | 当前行为 |
|---|---|---:|---|
| GET | `/api/health` | 200 | 服务与 SQLite 健康检查 |
| POST | `/api/profile/chat` | 200 | 对话抽取或更新画像 |
| GET | `/api/profile/{student_id}` | 200 | 获取最新画像 |
| POST | `/api/path/generate` | 200 | 生成或调整学习路径 |
| POST | `/api/resources/generate` | 202 | 创建并行五资源任务 |
| GET | `/api/tasks/{task_id}` | 200 | 查询任务状态 |
| GET | `/api/tasks/{task_id}/events` | 200 | SSE 任务事件 |
| POST | `/api/evaluation/submit` | 200 | Quiz 评分并完成画像、路径闭环 |
| GET | `/api/resources/{resource_id}` | 200 | 获取单项资源 |

OpenAPI 仍为 `/api/evaluation/submit` 保留 501 响应声明，这是冻结契约的一部分。当前正常业务路径不返回 501；有效提交返回 200，结构或归属问题返回统一错误。

## 3. 接口详情

### GET /api/health

```json
{
  "status": "ok",
  "service": "edu-agent-api",
  "version": "0.1.0",
  "environment": "development",
  "database": "ok"
}
```

### POST /api/profile/chat

请求必须携带截至本轮的完整对话历史，并在提交前加入最新用户消息。同一会话每轮保持同一个 `student_id`。

```json
{
  "student_id": "student-001",
  "conversation_id": "conversation-001",
  "messages": [
    {
      "message_id": "message-001",
      "role": "assistant",
      "content": "请介绍你的学习情况。"
    },
    {
      "message_id": "message-002",
      "role": "user",
      "content": "我是人工智能专业大二学生，正在学习机器学习。"
    }
  ],
  "evaluation_summary": null
}
```

响应包含 `profile`、`missing_dimensions`、`next_question`、`is_complete` 和 `extraction_mode`。

- 模型结构化成功：`llm_structured`
- 显式降级：`development_heuristic`

同一学生更新画像时创建 `version + 1`，历史版本保留。画像没有变化时，同一个 `next_question` 最多连续出现一次。

### GET /api/profile/{student_id}

返回最新 `StudentProfile`；不存在返回 404。

### POST /api/path/generate

```json
{
  "student_id": "student-001",
  "profile": null,
  "previous_path_id": null,
  "evaluation_summary": null
}
```

`profile=null` 时读取最新画像。初次规划返回 `adjustment_reason=null`；评价重规划会传入旧路径和评价摘要，返回的新路径必须说明 `adjustment_reason`。

- 模型结构化成功：`llm_structured`
- 显式降级：`development_rule_based`

### POST /api/resources/generate

```json
{
  "student_id": "student-001",
  "path_id": "path-id",
  "step": 1,
  "resource_types": [
    "explanation",
    "mind_map",
    "quiz",
    "reading",
    "coding"
  ],
  "regenerate": false
}
```

请求必须引用同一学生、最新画像版本和有效路径步骤。响应：

```json
{
  "task_id": "task-id",
  "status": "pending",
  "status_url": "/api/tasks/task-id",
  "events_url": "/api/tasks/task-id/events"
}
```

五类资源并行执行，单项失败不阻塞其他资源。任务终态：

- 全部请求资源通过审校：`completed`
- 至少一项成功且存在失败或 `needs_revision`：`partial_success`
- 没有可发布资源：`failed`

`regenerate=false` 允许命中进程内 TTL/LRU 缓存；`regenerate=true` 失效对应缓存键并重新生成。缓存只保存 `approved` 且不是 development fallback 的资源。命中后会复制为新资源 ID，Quiz 题目 ID 同步重写，并再次通过 Reviewer。

### GET /api/tasks/{task_id}

返回 `TaskState`；不存在返回 404。

### GET /api/tasks/{task_id}/events

响应类型为 `text/event-stream`。支持：

- 查询参数 `after=<sequence>`
- 请求头 `Last-Event-ID: <sequence>`

两者同时存在时从较大序号之后恢复。示例：

```text
id: 7
event: agent
data: {"sequence":7,"event_type":"agent","status":"completed","agent":"quiz_agent","resource_type":"quiz"}

```

业务事件的 `sequence` 连续且不重复。典型顺序：

1. task pending / started
2. Retriever started / completed
3. resource Agent started / completed 或 failed
4. Reviewer started / completed 或 failed
5. task completed / partial_success / failed

空闲时发送 SSE 注释心跳，不写入业务事件序列。所有终态事件发送完成后连接关闭。缓存命中通过安全日志及 Retriever 事件中的 `cache_hit=true` 识别，不增加公共字段。

### POST /api/evaluation/submit

题目 ID 必须来自当前学生、路径步骤对应的已持久化 Quiz：

```json
{
  "student_id": "student-001",
  "path_id": "path-id",
  "step": 1,
  "answers": [
    {
      "question_id": "resource-id::q1",
      "response": "A"
    }
  ],
  "time_spent_minutes": 12
}
```

Evaluation 使用资源中的真实答案计算分数和薄弱点，不按回答长度猜测正确性。若需要更新，它在同一请求内：

1. 写入 `evaluation` 来源的画像证据；
2. 保存 `version + 1` 画像；
3. 使用旧路径和评价摘要重新调用 Planner；
4. 保存带 `adjustment_reason` 的新路径；
5. 在建议对象中返回已持久化结果。

评价摘要被标记为系统评价，不会伪装为用户原话。

### GET /api/resources/{resource_id}

返回通过公共 `Resource` 校验并已持久化的资源；不存在返回 404。被 Reviewer 拒绝或审校执行失败的内容不会作为成功资源发布。

## 4. 错误格式

业务错误和请求校验错误统一使用：

```json
{
  "error": {
    "code": "PROFILE_NOT_FOUND",
    "message": "profile not found",
    "details": {}
  }
}
```

请求结构错误使用 `VALIDATION_ERROR`，字段详情位于 `error.details.validation_errors`。归属、路径步骤、题目来源等问题返回明确错误码，不回显 API Key 或完整模型响应。

## 5. 契约冻结与验证

任何实现不得修改这 9 个操作的路径、公共字段或枚举。自动测试会比较 OpenAPI 操作和公共 Schema；格式修复、缓存、私有 Draft、Reviewer 规则及内部事件说明均属于私有实现，不改变公共契约。
