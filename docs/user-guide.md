# EduAgent 用户指南

## 1. 运行要求

- Windows 10 或 Windows 11
- PowerShell 5.1 或 PowerShell 7
- Python 3.11 及以上
- Node.js 20 及以上
- npm 10 及以上
- Microsoft Edge 或 Chrome 最新稳定版

## 2. 首次安装

在仓库根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
Set-Location .\frontend
npm ci
Set-Location ..
Copy-Item .\.env.example .\.env
```

若要使用真实 DeepSeek，在根目录 `.env` 中配置模型开关、OpenAI 兼容地址、模型名称和本机 API Key。不要把 `.env` 复制到提交包、聊天记录或截图中。

## 3. 启动

### 一键启动

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1
```

脚本会先调用 `scripts/preflight_demo.py`，检查根目录 `.env`、Python、Node/npm、知识库、端口、公共契约和提交卫生，再启动前端与后端。可从仓库根目录或 `scripts` 目录运行；日志只写系统临时目录。保持窗口打开，按 `Ctrl+C` 停止服务。

### 手动启动

后端 PowerShell：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端 PowerShell：

```powershell
Set-Location .\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

访问：

- 前端：`http://127.0.0.1:5173/`
- 后端健康检查：`http://127.0.0.1:8000/api/health`

后端从项目根目录读取 `.env`。安全启动日志只显示模型开关、provider、model 和是否存在密钥。

## 4. 演示前预检与预热

在启动完整服务前先运行不会生成资源的预检：

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_demo.py
```

全部 PASS 后，如需验证真实模型连接，再运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_llm_profile_planner.py
```

该脚本验证 DeepSeek 连接及 Profile、Planner 的结构化输出，可以减少首次演示的连接冷启动影响。它不保存完整模型响应，也不输出密钥。

服务启动后可运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_end_to_end.py --verify-cache
.\.venv\Scripts\python.exe .\scripts\verify_resource_stability.py --runs 3
```

三个固定案例使用：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_demo_cases.py
```

案例脚本默认最多透明尝试 4 次；正式录制预检建议显式限制为 2 次。每次使用新的学生 ID，并在安全摘要中报告尝试次数和此前失败码。该策略只属于手动验证脚本，不改变产品 Agent 的一次格式修复上限。真实冷链路可能超过两分钟。

## 5. 核心使用流程

### 5.1 自然语言生成画像

在“学习画像”工作区用一段自然语言说明。系统支持中小学、大学、职业技能和兴趣学习场景：

- 学习阶段/专业和当前课程
- 已有基础
- 学习目标
- 薄弱知识点
- 资源和表达偏好
- 每天可用时间

系统把截至本轮的完整对话历史提交给 Profile Agent。信息充分时生成 10 个画像维度；信息不足时只追问一个关键问题。同一画像没有变化时，相同追问不会无限重复。

中小学场景优先询问年级、章节、考试目标和时间，不会要求填写大学专业。顶部“全科学习示例”只把示例写入输入框，不会自动发送；已有草稿时会先确认。点击“新建会话”会创建新的学生与会话 ID，并清空旧课程、画像、路径、资源、评价和进度。

点击画像字段可查看证据和置信度。模式标签含义：

- “结构化大模型结果”：`llm_structured`
- “开发适配器结果”：`development_heuristic`

助手消息不依赖输入框刷新；用户停止输入后回复仍会完整显示。

### 5.2 查看学习路径

画像完成后，系统调用 Planner。路径按步骤显示：

- 主题和学习目标
- 安排原因
- 推荐资源
- 完成标准
- 预计时间
- 前置知识

选择一个步骤作为资源目标。真实模型路径显示 `llm_structured`；显式规则降级显示 `development_rule_based`。

### 5.3 生成五类资源

进入“资源中心与学习评价”，点击生成全部资源。Orchestrator 并行执行：

1. 课程 RAG 检索；
2. Explanation；
3. MindMap；
4. Quiz；
5. Reading；
6. Coding（底层公共类型保持不变）；
7. Reviewer 逐项审校。

页面通过 SSE 自动显示检索、生成、审校和任务终态。网络短暂中断时会从最后 sequence 恢复；心跳不会显示为业务进度。

任务状态：

- `completed`：所有请求资源成功且通过审校。
- `partial_success`：至少一项资源成功，其他项失败或需要修改。
- `failed`：没有可发布资源。

单项失败不会隐藏其他成功资源。

### 5.4 查看资源

资源卡片显示：

- 标题
- 类型
- 目标知识点
- 难度
- 个性化原因
- 课程来源
- Reviewer 状态

支持的内容：

- 12 段结构化 Markdown 课程讲解与 FAQ
- 12 至 24 个节点的 Mermaid 思维导图
- 8 至 12 题的三层 Quiz 及解析
- 分层阅读路线、术语表和检查问题
- 计算机课程的代码实践；数学、理科和工程课程的计算与实验实践；语言、人文和艺术课程的应用实践任务

资源中心顶部的“本次学习资源包”会汇总主题、难度、五类完成情况、推荐学习顺序、当前路径步骤时间、RAG 来源数、Reviewer 通过数和 Evaluation 状态。`partial_success` 会列出缺失资源，已经成功的资源仍可继续使用。

资源详情中的“个性化依据”只读取当前画像的目标、薄弱点、资源偏好和时间预算。点击“学习追问建议”只会把问题填入对话输入框，不会自动发送；输入框已有草稿时会先确认。

本地知识库当前主要收录机器学习课程。只有与当前课程相关的真实命中才计入 RAG 来源数；未收录课程会显示“未命中本地课程资料，使用通用模型或学科规则生成”，不会使用机器学习资料凑数，也不会声称本地知识库覆盖所有教材。

`rejected` 资源不会作为可用学习内容显示。`needs_revision` 会明确标记，并使任务成为部分成功。

### 5.5 提交 Quiz 与动态调整

Quiz 包含 8 至 12 题，覆盖基础单选、进阶简答和挑战综合三个层次。题目导航会保留已填答案，显示完成进度，并在提交前定位第一道未作答题。提交后按钮锁定，Evaluation 根据数据库中的真实答案计算：

- 掌握度
- 是否通过
- 薄弱知识点
- 反馈与学习建议
- 每题结果、参考答案与解析；正确题显示为绿色，错误题显示为红色

需要调整时，后端在同一次 Evaluation 请求中完成画像版本递增和路径重规划。前端直接采用已持久化的新画像和新路径，不重复调用 Profile 或 Planner。评价证据显示为 `evaluation`，不是学生原话；新路径包含 `adjustment_reason`。

## 6. fallback 行为

真实模型不可用、超时、拒绝或输出校验失败时，系统保留可演示的明确降级：

- Profile：`development_heuristic`
- Planner：`development_rule_based`
- 资源：`personalization_reason` 中显示 `development fallback`

Quiz、MindMap 和 Reading 首次只发生安全格式错误时，会向模型请求一次格式修复。Profile 与 Planner 在结构或私有草稿校验失败时也最多请求一次完整 JSON 修复，并继续执行原有证据和路径约束。第二次失败后才进入对应的显式 fallback；网络、超时和安全拒绝不会触发格式修复。安全、事实、来源和 Reviewer 标准不会因此放宽，fallback 资源不会进入缓存。

## 7. 缓存行为

相同学生、画像版本、路径步骤、资源类型、模型版本和知识库版本可复用已审校资源。缓存默认在单个后端进程中保留 30 分钟，最多 128 项。

缓存命中仍会：

- 创建新的资源 ID；
- 为 Quiz 重写题目 ID；
- 再次执行 Reviewer；
- 在 SSE 检索消息中显示 `cache_hit=true`。

画像、路径、模型、课程资料或生成器版本变化后，旧缓存不会命中。需要强制重新生成时使用公共请求已有的 `regenerate=true`。

## 8. 三个固定演示案例

案例定义位于 `scripts/demo_cases.json`：

- A：高中数学基础型，突出函数、数列、图示、例题和期末目标。
- B：大学英语考试型，突出词汇、阅读、写作、练习与纠错。
- C：项目实践型，突出逻辑回归、模型选择、调参与代码实验，作为最终录制推荐案例。

详细预期和讲解方式见 `docs/demo-script.md`。

## 9. 常见问题

### 页面显示无法连接后端

确认后端在 `127.0.0.1:8000` 运行，并访问 `/api/health`。检查端口是否被其他程序占用。

### 页面一直显示加载中

查询任务状态。正常任务一定收敛到 `completed`、`partial_success` 或 `failed`。SSE 中断时前端会重连并使用轮询兜底。

### 思维导图无法显示

页面会保留原始 Mermaid 文本和错误提示。其他资源不受影响。重新生成前先查看 Reviewer 状态和后端安全日志。

### 资源显示 development fallback

这表示结构化资源生成未成功，系统使用了本地规则内容。机器学习课程可能引用本地知识库；其他学科未命中本地资料时会明确显示“通用生成”标记。该资源仍经过 Reviewer，但不能被描述为 DeepSeek 生成结果，也不能把通用生成标记说成真实课程来源。

### 第二次生成明显更快

检查 SSE 是否出现 `cache_hit=true`。只有相同缓存键才能复用；这代表使用已审校资源快照，不代表模型调用速度提升。

### Evaluation 提交失败

必须提交当前学生、当前路径步骤下持久化 Quiz 的题目 ID。旧资源、其他学生或手写题目 ID 会被拒绝。
