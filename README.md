# EduAgent

EduAgent 是面向中国软件杯 A3 赛题的多智能体个性化学习系统。当前公共基线提供自然语言学习画像、个性化学习路径、SQLite 持久化、资源任务编排协议、任务状态和 SSE 进度；Profile Agent 与 Planner Agent 已支持统一客户端驱动的结构化 LLM 输出。五类真实资源 Agent、Reviewer 和 Evaluation 将由后续阶段接入。

## 项目结构

```text
backend/app/api            FastAPI接口与统一错误处理
backend/app/schemas        公共数据契约
backend/app/profile        Profile Agent
backend/app/planner        Planner Agent
backend/app/llm            统一LLM协议、兼容客户端与测试Fake
backend/app/orchestrator   Agent协议、注册和任务编排
backend/app/database       SQLite与仓储
backend/tests              自动化公共契约测试
frontend                   Agent 3前端入口
data/machine_learning      Agent 2课程知识库入口
docs                       架构、API和交接文档
```

公共模型名称固定为 `Resource`（学习资源实体）和 `TaskState`（资源生成任务状态实体）。禁止重复创建 `LearningResource`、`GenerationTask` 等同义模型。

## 运行环境

- Python 3.11及以上
- 当前验收环境：Python 3.13.5
- SQLite（Python标准库自带）

## 安装依赖

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
```

## 环境变量

```powershell
Copy-Item .\.env.example .\.env
```

关键配置：

- `DATABASE_URL=sqlite:///./data/eduagent.db`：相对仓库根目录解析，与当前工作目录无关。
- `EDUAGENT_ALLOWED_ORIGINS`：前端允许来源。
- `ENABLE_LLM=true`：启用结构化 LLM 尝试；设为 `false` 时直接使用 development 降级实现。
- `LLM_PROVIDER=openai_compatible`：当前支持 `openai_compatible` 和 `dashscope`（OpenAI 兼容接口）。
- `LLM_API_KEY`：必须留在被忽略的 `.env` 或系统环境变量，严禁提交真实密钥。
- `LLM_MODEL`、`LLM_BASE_URL`：模型名称与兼容接口基地址。
- `LLM_TIMEOUT_SECONDS=30`、`LLM_MAX_RETRIES=1`：单次超时与有限重试次数。

## 启动

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file ..\.env
```

不创建 `.env` 时也可使用安全默认配置启动。

## 测试

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
```

## API文档

- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`
- 健康检查：`http://127.0.0.1:8000/api/health`
- 详细契约：[docs/api-spec.md](docs/api-spec.md)

## 当前真实功能

- FastAPI公共API和统一结构校验。
- 学生画像版本、学习路径、任务、事件和资源的SQLite持久化。
- Profile Agent 基于结构化 LLM 输出抽取画像，校验证据原文、来源分类、置信度和画像版本。
- Planner Agent 基于结构化 LLM 输出生成有序路径，校验时间预算、前置关系、总时长与重复步骤。
- LLM 客户端统一封装供应商配置、超时、有限重试、异常分类和 Pydantic 结构校验。
- Orchestrator并行调用协议、单Agent失败隔离、Reviewer逐资源审校流程。
- 持久化任务状态与SSE事件。

## 当前development功能

- Profile Agent 降级实现：未配置密钥、超时、网络、内容安全拒绝、JSON 或 Schema 校验失败时使用 `development_heuristic`；真实成功使用冻结枚举 `llm_structured`。
- Planner Agent 降级实现：相同故障条件下使用 `development_rule_based`；真实成功使用冻结枚举 `llm_structured`。当前知识库尚未接入，Planner 不声称已执行知识库检索。
- Evaluation接口：当前明确返回501和 `mock=true`。
- 五类资源Agent及Reviewer：当前未注册；不会返回假资源。

## Agent 2开发入口

- 实现 `backend/app/rag`、`resources`、`guardrails`、`evaluation` 和课程数据。
- 在 `backend/app/resources/registry.py` 暴露 `register_agents(registry)`。
- 实现 `ResourceAgent.generate(SharedAgentContext) -> Resource` 和 `ReviewerAgent.review(...) -> Resource`。
- 直接复用 `backend/app/schemas`，不得复制公共模型。

## Agent 3开发入口

- API基地址：`http://127.0.0.1:8000/api`。
- 画像字段读取 `value`、`evidence`、`confidence`。
- 资源任务创建后连接返回的 `events_url`，按 `sequence` 去重并处理 `partial_success`。
- 详细请求、响应和枚举以 `docs/api-spec.md` 与 `/openapi.json` 为准。
