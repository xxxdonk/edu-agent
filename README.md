# EduAgent

EduAgent 是面向中国软件杯 A3 赛题的多智能体个性化学习系统。它从自然语言对话建立带证据的学生画像，生成个性化学习路径，并通过课程知识库、五类资源 Agent、Reviewer、SSE 和 Evaluation 完成“学习—练习—评价—画像更新—路径重规划”闭环。

当前公共契约为 `api-contract-v0.1`：9 个 API 操作、公共 Schema、字段和枚举均已冻结。运行时模型通过 OpenAI 兼容协议接入 DeepSeek；没有可用模型服务时，系统会明确显示 development 降级，绝不把本地规则结果冒充为大模型结果。

## 已实现能力

- Profile Agent：完整对话历史驱动的结构化画像，保存字段级证据、置信度和版本。
- Planner Agent：依据画像、薄弱点、目标和时间预算生成有序路径，评价后可重新规划。
- 课程 RAG：加载 `data/machine_learning/` 中的课程章节和来源清单，返回可追溯引用。
- 五类资源 Agent：`explanation`、`mind_map`、`quiz`、`reading`、`coding` 并行生成。
- Reviewer：逐项检查来源、个性化、Markdown、Mermaid、Python、Quiz 一致性和内容安全。
- Orchestrator：单项失败隔离、`completed | partial_success | failed` 终态和可恢复 SSE。
- Evaluation：使用持久化 Quiz 答案评分，以 `evaluation` 证据更新画像并重新规划路径。
- 前端工作台：对话、画像、路径、实时进度、五类资源和评价闭环展示。
- 资源缓存：仅缓存通过 Reviewer 且不是 development fallback 的资源；缓存命中仍创建新资源 ID 并重新审校。

## 项目结构

```text
backend/app/api            FastAPI 接口、SSE 与统一错误处理
backend/app/schemas        冻结的公共数据契约
backend/app/profile        Profile Agent
backend/app/planner        Planner Agent
backend/app/llm            OpenAI 兼容模型客户端
backend/app/orchestrator   并行编排、任务状态与进程内缓存
backend/app/rag            课程知识库加载、检索和版本摘要
backend/app/resources      五类资源 Agent 与 Reviewer
backend/app/evaluation     Quiz 评分与学习反馈
backend/app/database       SQLite 与仓储
frontend                   Vue 3 学习工作台
data/machine_learning      机器学习课程资料与来源索引
scripts                    启动、预热、端到端和演示案例验证
docs                       API、架构、测试、使用与合规文档
```

公共实体名称固定为 `Resource` 和 `TaskState`，不得创建同义公共模型。

## Windows 环境

- Windows 10 或 Windows 11
- PowerShell 5.1 或 PowerShell 7
- Python 3.11 及以上
- Node.js 20 及以上
- npm 10 及以上
- Microsoft Edge 或 Chrome 最新稳定版

在仓库根目录安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
Set-Location .\frontend
npm ci
Set-Location ..
```

复制配置模板：

```powershell
Copy-Item .\.env.example .\.env
```

真实模型演示需要在根目录 `.env` 中配置 `ENABLE_LLM`、`LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`。DeepSeek 使用 `openai_compatible` 供应商协议。真实密钥只能保存在本机 `.env` 或系统环境变量中；启动日志只输出是否存在密钥，不输出密钥内容。

常用缓存配置：

- `EDUAGENT_RESOURCE_CACHE_ENABLED`：默认启用。
- `EDUAGENT_RESOURCE_CACHE_TTL_SECONDS`：默认 1800 秒。
- `EDUAGENT_RESOURCE_CACHE_MAX_ENTRIES`：默认 128 项。

缓存键包含学生 ID、画像版本及指纹、路径 ID、步骤及指纹、资源类型、模型标识、知识库版本和生成器修订号。画像、路径、模型、知识库或生成逻辑变化后不会误用旧缓存；请求中的 `regenerate=true` 会绕过并失效当前键。缓存是单进程内存缓存，服务重启后自然清空。

## 一键启动

依赖安装完成后，在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1
```

脚本检查 Python、npm、前端依赖和端口后，以隐藏子进程启动后端和前端。保持 PowerShell 窗口打开；按 `Ctrl+C` 同时停止两个服务。脚本不读取或打印 API Key，运行日志写入系统临时目录。

打开：

- 前端：`http://127.0.0.1:5173/`
- 健康检查：`http://127.0.0.1:8000/api/health`
- Swagger：`http://127.0.0.1:8000/docs`

## 手动启动

后端窗口：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端始终从项目根目录加载 `.env`，与当前工作目录无关。

前端窗口：

```powershell
Set-Location .\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

## 模型预热与验证

服务启动前可先验证 Profile 和 Planner 的真实结构化调用：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_llm_profile_planner.py
```

该脚本可作为模型连接预热，不保存完整响应，也不输出密钥。完整服务启动后运行真实端到端验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_end_to_end.py --verify-cache
.\.venv\Scripts\python.exe .\scripts\verify_resource_stability.py --runs 3
```

运行三个固定演示案例：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_demo_cases.py
```

案例数据保存在 `scripts/demo_cases.json`。验证脚本为每个案例创建唯一学生 ID，只输出安全摘要。为应对真实模型波动，每个案例默认最多透明尝试 4 次；输出会保留尝试次数和此前失败码，不会把失败伪装成首次成功。

## 自动测试与构建

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location .\frontend
npm test -- --run
npm run build
```

当前封版结果为后端 109 passed、前端 24/24 passed，TypeScript 与 Vite 生产构建通过。自动测试使用 Fake LLM 或本地实现，不访问真实网络。详细结果见 [docs/test-report.md](docs/test-report.md)。

启动演示前可先执行不会生成资源的安全预检：

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_demo.py
```

预检只报告环境、依赖、端口、知识库、公共契约和提交卫生状态；API Key 只检查是否存在，不显示值。一键启动脚本会自动调用该预检，从仓库根目录或 `scripts` 目录运行都使用脚本自身位置定位项目。

## 资源格式修复与 fallback

Quiz、MindMap 和 Reading 使用各自的私有 Draft，不改变公共 `Resource`：

- Quiz 固定生成 3 题：基础单选、进阶简答、挑战综合。
- MindMap 的最终内容只保留 Mermaid `mindmap` 正文。
- Reading 固定为概览、3 个核心要点、实践联系和后续学习。

系统只归一化明确且安全的问题，例如单选标签、外层 Mermaid 代码围栏、换行和列表前缀。Quiz、MindMap、Reading 首次输出发生纯格式错误时，最多追加一次“只修复格式”的模型请求；网络、超时、安全或事实问题不会走格式修复。第二次仍失败时使用明确标记的 `development fallback`，随后仍接受公共 Schema 和 Reviewer 的完整校验。

Profile 和 Planner 对无效结构同样最多补发一次完整 JSON 修复请求，业务校验不放宽；再次失败或发生网络、超时、安全问题时立即使用既有显式降级。Profile 的降级模式为 `development_heuristic`，Planner 的降级模式为 `development_rule_based`。界面、资源个性化原因和安全日志会显示降级，便于演示时区分真实结果。

Profile 在内部边界把带明确标签的评价主题归一化为纯知识点名称，同时保留原始 `source=evaluation` 证据；普通主题中的中文冒号不会被截断。Planner 案例 C 的评价后重规划曾连续三次保持 `llm_structured`，但 DeepSeek 仍可能波动，正式录制以案例 B 为主、案例 C 作为代码实践备用，并在录制前执行预检。真实冷链路可能超过两分钟。

## 文档

- [API 契约](docs/api-spec.md)
- [系统架构](docs/architecture.md)
- [用户指南](docs/user-guide.md)
- [测试报告](docs/test-report.md)
- [演示脚本](docs/demo-script.md)
- [开源软件与课程来源](docs/open-source-licenses.md)
- [AI 编码工具使用声明](docs/ai-coding-tool-statement.md)
