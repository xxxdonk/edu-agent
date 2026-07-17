# EduAgent 用户指南

## 1. 运行环境

- Python 3.11 及以上
- Node.js 20 及以上
- npm 10 及以上
- 推荐浏览器：Microsoft Edge 或 Chrome 最新稳定版

## 2. 启动后端

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
Copy-Item .\.env.example .\.env
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file ..\.env
```

访问 `http://127.0.0.1:8000/api/health`，确认 `status` 和 `database` 均为 `ok`。

真实模型演示需在仓库根目录 `.env` 中配置 `ENABLE_LLM=true`、模型地址、模型名称和密钥。不要将 `.env` 提交到 Git。

## 3. 启动前端

新开一个 PowerShell 窗口，在仓库根目录执行：

```powershell
Set-Location .\frontend
Copy-Item .\.env.example .\.env
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`。页面右上角应显示后端版本、数据库状态和运行环境。

## 4. 核心使用流程

### 4.1 对话生成学习画像

在“学习画像工作区”用自然语言描述专业、课程基础、学习目标、薄弱点、偏好和可用时间。系统会逐字展示回复，并生成 10 个画像维度。

点击任一画像维度的“查看字段证据”，可查看证据来源和原始话语。若信息不足，页面会展示缺失维度，EduAgent 会继续自然语言追问。

### 4.2 查看个性化学习路径

画像更新后，系统自动调用 Planner Agent。进入“个性化学习路径工作区”，查看每一步的主题、目标、安排原因、推荐资源、前置知识、预计时间和完成标准。

点击一个步骤将其设为当前资源生成目标。评价触发路径调整后，评价区会展示更新前后对比。

### 4.3 生成五类学习资源

进入“资源中心与学习评价”，点击“生成五类资源”。页面通过 SSE 展示 Profile、Planner、Retriever、五个资源 Agent、Reviewer 和 Orchestrator 的状态。

任务完成后可依次查看：

- Markdown 课程讲解
- Mermaid 思维导图
- 分层练习题
- 拓展阅读
- Python 代码实践

每项资源均显示目标知识点、难度、个性化原因、知识库来源、审校状态和创建时间。单个资源失败时，其他成功资源仍会保留。

### 4.4 提交练习并动态调整

完成分层练习后提交答案。页面展示掌握度总分、逐题结果、参考答案、解析、薄弱知识点和学习建议。

当评价结果要求更新时，前端会将评价摘要再次提交给 Profile Agent，并带旧路径 ID 调用 Planner Agent，随后展示画像和路径更新前后差异。

## 5. 状态说明

- “结构化大模型结果”：本次画像或路径来自真实结构化 LLM 调用。
- “开发适配器结果”：后端未配置模型或模型调用失败，结果来自公开标记的开发降级逻辑。
- “部分成功”：至少一项资源失败，成功资源仍可使用。
- “需修改”：Reviewer 发现来源、难度、个性化或内容完整性问题。

系统不使用固定结果冒充真实接口。接口异常会以中文提示，并在页面底部“后端接口问题记录”中保存请求、预期响应、实际响应和复现步骤。

## 6. 常见问题

前端显示“无法连接学习服务”：确认后端运行于 `127.0.0.1:8000`，并检查 `frontend/.env` 的 `VITE_API_BASE_URL`。

思维导图无法显示：页面会保留原始 Mermaid 文本。检查资源的 `content_format` 是否为 `mermaid`，以及内容是否符合 Mermaid 语法。

资源生成后没有内容：查看 Agent 轨迹、任务终态和接口问题记录；`partial_success` 不应隐藏已有成功资源。

评价显示开发接口提示：当前后端评价 Agent 尚未成功返回正式 `EvaluationResult`，前端不会加载伪造评价。
