# EduAgent API 契约

版本：0.1.0  
状态：Day 1 冻结基线  
Base URL：`http://127.0.0.1:8000`  
OpenAPI：`/docs`、`/openapi.json`

除 SSE 外，所有请求和响应使用 `application/json; charset=utf-8`。时间均为带时区的 ISO 8601 UTC 字符串。未列出的字段默认不接受。

## 0. 安装与启动

在项目根目录执行（Windows PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
Copy-Item .\.env.example .\.env
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --env-file ..\.env
```

启动后访问 `http://127.0.0.1:8000/api/health`。配置项见项目根目录 `.env.example`；`DATABASE_URL=sqlite:///./data/eduagent.db` 中的相对路径始终相对仓库根目录解析，与启动工作目录无关。真实 `.env` 和数据库文件已加入 `.gitignore`。

## 1. 枚举

- `Difficulty`：`beginner | intermediate | advanced`
- `ResourceType`：`explanation | mind_map | quiz | reading | coding`
- `ReviewStatus`：`pending | approved | rejected | needs_revision`
- `TaskStatus`：`pending | running | completed | partial_success | failed`
- `AgentRunStatus`：`pending | started | completed | failed | skipped`

公共模型名称固定为：

- `Resource`：学习资源实体。不得另建 `LearningResource` 同义模型。
- `TaskState`：资源生成任务状态实体。不得另建 `GenerationTask` 同义模型。

资源类型与展示名称映射：

| resource_type | 中文名称 | 建议 content_format |
|---|---|---|
| `explanation` | 课程讲解文档 | `markdown` |
| `mind_map` | 思维导图 | `mermaid` |
| `quiz` | 分层练习题 | `json` 或 `markdown` |
| `reading` | 拓展阅读 | `markdown` |
| `coding` | 代码实践案例 | `python` 或 `markdown` |

## 2. 公共数据模型

### 2.1 ProfileField

每个画像维度都必须包含值、字段级证据和置信度；不允许仅在画像顶层提供一份笼统证据。

```json
{
  "value": "计算机科学与技术",
  "evidence": [
    {
      "source": "conversation",
      "quote": "我是计算机专业大二学生",
      "message_id": "msg-1"
    }
  ],
  "confidence": 0.78
}
```

`source` 为 `conversation | evaluation | inference | system_default`，`confidence` 范围为 0 到 1。直接对话事实使用 `conversation`；由对话归一化推断出的水平、认知风格等使用 `inference` 并降低置信度；默认值使用 `system_default`。

### 2.2 StudentProfile

```json
{
  "student_id": "stu-001",
  "version": 1,
  "major": {"value": "计算机科学与技术", "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "course": {"value": "机器学习", "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "knowledge_level": {"value": "beginner", "evidence": [{"source": "inference", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.72},
  "learning_goals": {"value": ["完成课程项目"], "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "weak_topics": {"value": ["梯度下降"], "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "learning_history": {"value": ["学过Python"], "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "cognitive_style": {"value": "practice_oriented", "evidence": [{"source": "inference", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.68},
  "language_preference": {"value": "中文", "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.78},
  "resource_preference": {"value": ["代码实践案例"], "evidence": [{"source": "inference", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}], "confidence": 0.68},
  "time_budget": {
    "value": {"minutes_per_day": 45, "days_per_week": 5},
    "evidence": [{"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}],
    "confidence": 0.78
  },
  "evidence": [
    {"source": "conversation", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"},
    {"source": "inference", "quote": "我是计算机专业学生，正在学机器学习，零基础，梯度下降薄弱，学过Python，偏好中文、代码和动手实践，每天45分钟、每周5天，希望完成课程项目。", "message_id": "msg-1"}
  ],
  "confidence": 0.754,
  "updated_at": "2026-07-15T08:00:00Z"
}
```

### 2.3 LearningPathStep / LearningPath

每一步必须包含：

```json
{
  "step": 1,
  "topic": "梯度下降",
  "learning_goal": "理解并实现梯度下降",
  "reason": "画像显示该主题是当前薄弱点",
  "recommended_resources": ["explanation", "mind_map", "quiz", "coding"],
  "completion_criteria": ["能解释更新公式", "练习正确率达到80%"],
  "estimated_minutes": 45,
  "prerequisites": []
}
```

LearningPath 还包含 `path_id`、`student_id`、`profile_version`、`course`、`status`、`steps`、`adjustment_reason`、`generation_mode` 和 `created_at`。

### 2.4 Resource

```json
{
  "resource_id": "res-uuid",
  "resource_type": "explanation",
  "title": "面向计算机专业初学者的梯度下降",
  "content": "# 梯度下降……",
  "content_format": "markdown",
  "target_topic": "梯度下降",
  "difficulty": "beginner",
  "personalization_reason": "学生偏好代码实践且该主题薄弱",
  "source_references": [
    {
      "source_id": "ml-syllabus",
      "title": "机器学习基础课程大纲",
      "locator": "data/machine_learning/syllabus.md#梯度下降",
      "chunk_id": "chunk-12"
    }
  ],
  "review_status": "approved",
  "created_at": "2026-07-15T08:00:00Z"
}
```

`source_references` 至少一项。知识库没有可靠依据时不得伪造引用。

### 2.5 TaskState / TaskEvent

TaskState 包含：`task_id`、`task_type`、`student_id`、`status`、`progress`、`current_stage`、`requested_resource_types`、`result_resource_ids`、`agent_runs`、`errors`、`created_at`、`updated_at`。

TaskEvent 包含：`event_id`、`task_id`、`sequence`、`event_type`、`status`、`progress`、`message`、`agent`、`resource_type`、`error`、`created_at`。

### 2.6 EvaluationSubmission / EvaluationResult

提交字段：`student_id`、`path_id`、`step`、`answers[{question_id,response}]`、`time_spent_minutes`。

结果字段：`evaluation_id`、`student_id`、`path_id`、`step`、`mastery_score`、`passed`、`weak_topics`、`feedback`、`profile_update_required`、`path_update_required`、`evaluated_at`。

## 3. 错误格式

业务错误使用：

```json
{
  "error": {
    "code": "PROFILE_NOT_FOUND",
    "message": "profile not found: stu-001",
    "details": {"id": "stu-001"}
  }
}
```

HTTP 业务错误和请求结构校验错误均统一使用以上 `error` 外层。结构校验错误的 `code` 为 `VALIDATION_ERROR`，具体字段错误位于 `error.details.validation_errors`。

## 4. API 清单

| 方法 | 路径 | 成功状态 | 用途 | 第一阶段状态 |
|---|---|---:|---|---|
| GET | `/api/health` | 200 | 服务与数据库健康检查 | 已实现 |
| POST | `/api/profile/chat` | 200 | 对话提取/更新画像并返回追问 | 结构化LLM；失败时显式降级 |
| GET | `/api/profile/{student_id}` | 200 | 获取最新画像版本 | 已实现 |
| POST | `/api/path/generate` | 200 | 生成或调整学习路径 | 结构化LLM；失败时显式降级 |
| POST | `/api/resources/generate` | 202 | 创建五类资源异步任务 | 编排骨架已实现，等待 Agent 2 注册 |
| GET | `/api/tasks/{task_id}` | 200 | 查询任务状态 | 已实现 |
| GET | `/api/tasks/{task_id}/events` | 200 | SSE 获取任务事件 | 已实现 |
| POST | `/api/evaluation/submit` | 200 | 提交答题并更新画像/路径 | 契约已固定，当前明确返回 501 |
| GET | `/api/resources/{resource_id}` | 200 | 获取单项资源 | 已实现 |

## 5. 接口详情

### GET /api/health

响应示例：

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

请求：

```json
{
  "student_id": "stu-001",
  "conversation_id": "conv-001",
  "messages": [
    {
      "message_id": "msg-001",
      "role": "user",
      "content": "我是计算机专业学生，机器学习零基础，梯度下降不太懂。每天能学45分钟，喜欢边写代码边学，希望完成课程项目。"
    }
  ],
  "evaluation_summary": null
}
```

响应：`profile`（StudentProfile）、`missing_dimensions`、`next_question`、`is_complete`、`extraction_mode`。如果关键信息不足，`next_question` 必须是自然语言追问；不得使用传统问卷替代对话。

同一 `student_id` 再次提交会创建 `version + 1` 的新画像，旧版本保存在数据库中。

`extraction_mode` 严格使用冻结枚举：结构化 LLM 成功为 `llm_structured`；配置缺失、网络/超时、安全拒绝、JSON 或 Schema 校验失败时为 `development_heuristic`。降级不会改变响应结构，也不得被解释为真实 LLM 结果。

### GET /api/profile/{student_id}

返回最新 StudentProfile。不存在返回 404。

### POST /api/path/generate

请求：

```json
{
  "student_id": "stu-001",
  "profile": null,
  "previous_path_id": null,
  "evaluation_summary": null
}
```

`profile` 为空时读取数据库中的最新画像。调整路径时传 `previous_path_id` 和 `evaluation_summary`。响应为 `{"path": LearningPath}`。

`generation_mode` 严格使用冻结枚举：结构化 LLM 成功为 `llm_structured`；降级为 `development_rule_based`。当前 Planner 未接入课程知识库，不会在路径内容中声称已执行知识库检索。

### POST /api/resources/generate

请求：

```json
{
  "student_id": "stu-001",
  "path_id": "path-uuid",
  "step": 1,
  "resource_types": ["explanation", "mind_map", "quiz", "reading", "coding"],
  "regenerate": false
}
```

响应 202：

```json
{
  "task_id": "task-uuid",
  "status": "pending",
  "status_url": "/api/tasks/task-uuid",
  "events_url": "/api/tasks/task-uuid/events"
}
```

请求必须引用同一学生的有效画像、路径和步骤。单个资源失败时任务可为 `partial_success`，成功资源仍可读取。

### GET /api/tasks/{task_id}

返回 TaskState。前端可轮询，但核心演示优先使用 SSE。

### GET /api/tasks/{task_id}/events

响应类型：`text/event-stream`。可用查询参数 `after=<sequence>` 或请求头 `Last-Event-ID` 续传。

```text
id: 3
event: agent
data: {"event_id":"...","task_id":"...","sequence":3,"event_type":"agent","status":"completed","progress":34,"message":"explanation_agent 已完成","agent":"explanation_agent","resource_type":"explanation","error":null,"created_at":"..."}

```

事件顺序：任务 pending → Orchestrator started → 各 Agent started/completed/failed → Reviewer started/completed/failed/skipped → 任务终态。连接在任务到达终态且事件发送完毕后关闭；空闲连接每15秒发送 SSE 注释心跳。

### POST /api/evaluation/submit

请求：

```json
{
  "student_id": "stu-001",
  "path_id": "path-uuid",
  "step": 1,
  "answers": [{"question_id": "q-1", "response": "..."}],
  "time_spent_minutes": 12
}
```

目标响应为 EvaluationResult，并由 Evaluation Agent 触发画像版本和路径更新。第一阶段当前返回 501，响应 `details.mock=true`，不得被前端当作评价成功。

### GET /api/resources/{resource_id}

返回 Resource。资源未生成或不存在时返回 404。

## 6. Agent 2 集成契约

Agent 2 需创建 `backend/app/resources/registry.py` 并暴露：

```python
def register_agents(registry):
    registry.register_resource(explanation_agent)
    registry.register_resource(mind_map_agent)
    registry.register_resource(quiz_agent)
    registry.register_resource(reading_agent)
    registry.register_resource(coding_agent)
    registry.register_reviewer(reviewer_agent)
```

每个资源 Agent：

- 实现 `agent_name`、`resource_type`、`async generate(SharedAgentContext) -> Resource`。
- 使用 `context.profile`、`context.path`、`context.request.step`，不得重新定义画像或路径模型。
- 资源返回必须使用公共 `Resource`，任务状态必须使用公共 `TaskState`；禁止创建 `LearningResource`、`GenerationTask` 同义模型。
- 返回值必须通过 Resource 校验，尤其是至少一个真实 `source_references`。
- 缺少知识库依据时抛出可读异常；Orchestrator 会隔离失败并记录事件。
- Reviewer 在五类生成结束后运行，返回更新过 `review_status` 的 Resource。

Evaluation Agent 应接受 EvaluationSubmission、返回 EvaluationResult，并把结果摘要交给 Profile/Planner 更新；实现前请与 Agent 1 联调，不要自行改接口字段。

## 7. Agent 3 前端契约

- 对话页提交完整或增量消息数组，展示字段级 confidence/evidence、缺失维度和 `next_question`。
- 路径页按 `step` 升序展示 topic、reason、资源、时间、完成标准和 prerequisites。
- 创建资源任务后立即连接 `events_url`，按 `sequence` 去重；断线时传 `Last-Event-ID`。
- 进度条使用 TaskEvent.progress；每个 Agent 使用 `agent + resource_type + status` 展示轨迹。
- 终态后读取 TaskState.result_resource_ids，再逐项请求资源。
- 必须正确展示 `partial_success` 与每项 errors，不能因单项失败隐藏成功资源。
- 第一阶段遇到 `details.mock=true` 或 mode 以 `development_` 开头时，在开发界面标记为“开发适配器结果”。

## 8. 契约变更规则

任何字段、枚举、状态或路径变更必须同时修改 `backend/app/schemas` 与本文，并通知 Agent 2、Agent 3。Day 1 后优先只做向后兼容的可选字段扩展；禁止三个成员各自维护同名模型。
