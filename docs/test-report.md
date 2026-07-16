# EduAgent 前端与集成测试报告

测试日期：2026-07-16

测试分支：`agent/frontend-day2-integration`

基线：`develop@19d09be`

## 1. 测试环境

| 项目 | 版本或地址 |
|---|---|
| Windows | 本地开发环境 |
| Python | 3.13.3 |
| Node.js | 24.15.0 |
| npm | 11.12.1 |
| 前端 | `http://127.0.0.1:5173/` |
| 后端 | `http://127.0.0.1:8001/`（联调端口） |

后端未配置 LLM 密钥，因此本机闭环使用后端明确标记的
`development_heuristic` 和 `development_rule_based` 降级模式。Agent 1 在合并请求 #5
中已报告真实 DeepSeek Profile 链路返回 `llm_structured`，本报告不把本机降级结果描述为真实 LLM 结果。

## 2. 自动化结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端回归 | `cd backend; ..\.venv\Scripts\python.exe -m pytest -q` | 48 通过，1 条依赖弃用警告 |
| 前端单元测试 | `cd frontend; npm test` | 3 个文件、11 个测试全部通过 |
| TypeScript 与生产构建 | `cd frontend; npm run build` | 通过，3385 个模块完成转换 |

生产构建仍有大于 500 kB 的 chunk 警告，不阻断比赛局域网演示。Mermaid 已动态导入，
后续如需优化首屏体积，可再拆分 Element Plus 与图表依赖。

## 3. 真实接口闭环

本轮使用最新 `develop` 后端，不修改后端核心业务代码。测试输入为计算机专业、机器学习、
梯度下降薄弱、偏好中文/思维导图/代码实践、每天 45 分钟且目标为完成课程项目的自然语言描述。

| 验证项 | 实际结果 | 状态 |
|---|---|---|
| `GET /api/health` | 服务和数据库均为 `ok` | 通过 |
| `POST /api/profile/chat` | 生成含字段证据和置信度的完整画像 | 通过 |
| `POST /api/path/generate` | 生成 2 至 3 个有序步骤 | 通过 |
| `POST /api/resources/generate` | 异步任务到达 `completed` | 通过 |
| SSE | 页面接收 15 条持久化事件并按 sequence 去重 | 通过 |
| 五类资源 | explanation、mind_map、quiz、reading、coding 各 1 项 | 通过 |
| Markdown / 代码高亮 | 内容正常渲染 | 通过 |
| Mermaid | 代码围栏内容经兼容提取后生成 SVG | 通过 |
| `POST /api/evaluation/submit` | 错误答案得到 0 分、逐题解析和薄弱点 | 通过 |
| 动态调整 | 评价后再次调用画像和路径接口并显示前后对比 | 通过 |

## 4. 浏览器端演示回归

Edge Headless 在 `1440x1000` 视口完成以下操作：新建会话、自然语言对话、画像生成、
学习路径查看、五类资源生成、Agent 轨迹、Mermaid SVG、4 道练习提交、0 分反馈以及画像/路径更新。

关键观测值：`resourceCount=5`、`quizQuestions=4`、`eventCount=15`、
`mermaidRendered=true`、`documentWidth=1425`、`viewportWidth=1440`，未出现横向溢出。

已覆盖初始、加载、Agent 生成、成功、部分成功、全部失败、空结果、网络错误、30 秒 REST 超时、
后端异常、Mermaid 失败回退、SSE 重连、轮询兜底和重试生成。单项资源失败不会清空其他成功资源。

## 5. 本轮修复

### FE-001：SSE 在首个 Agent 完成时提前关闭

- 原因：前端把任意事件的 `completed` 都当作整个任务终态。
- 修复：仅当 `event_type=task` 且状态为 `completed | partial_success | failed` 时关闭连接。
- 回归：修复前页面仅显示 4 条事件；修复后稳定显示全部 15 条事件和 Reviewer 状态。

### FE-002：Mermaid 资源无法渲染

- 原因：后端 `content_format=mermaid` 的内容仍包含 Markdown 代码围栏和尾部 HTML 注释。
- 修复：渲染前提取 Mermaid 围栏正文并移除注释，失败时仍显示清洗后的原始内容。
- 回归：真实接口返回的 mindmap 已生成 SVG；新增围栏与原始源码两类单元测试。

## 6. 后端接口问题

### BE-002：评价接口只返回更新标志，未直接持久化画像与路径

- 接口地址：`POST /api/evaluation/submit`
- 请求参数：`EvaluationSubmission`
- 预期响应：返回 `EvaluationResult`，并按 API 文档触发画像版本和路径更新。
- 实际响应：返回评价和两个 `update_required` 标志，未在接口内部完成后续持久化更新。
- 浏览器报错：无；前端需要额外调用 `/api/profile/chat` 和 `/api/path/generate`。
- 复现步骤：生成 quiz；提交错误答案；检查评价响应；查询画像与路径版本。
- 当前兼容：前端根据标志完成两次真实调用并展示前后对比，需由系统集成负责人确认最终职责边界。

### BE-003：Python 代码资源偶发无法通过 Reviewer 语法检查

- 接口地址：`POST /api/resources/generate`、`GET /api/resources/{resource_id}`
- 请求参数：包含 coding 的 `ResourceGenerationRequest`；资源 ID
  `345214e0-0265-4d00-b949-b4a74a397920`。
- 预期响应：可执行 Python 内容，Reviewer 状态为 `approved`。
- 实际响应：资源为 `needs_revision`，后端日志记录
  `invalid character '½' (U+00BD) (行 14)`。
- 浏览器报错：页面不崩溃，资源卡显示“需修改”；代码无法直接执行。
- 复现步骤：构建机器学习画像与路径；生成五类资源；打开 Python 代码实践；检查审校状态和后端日志。
- 状态：已反馈，未修改后端。

### BE-004：Mermaid 内容格式与 `content_format` 不一致

- 接口地址：`GET /api/resources/{resource_id}`
- 请求参数：mind_map 资源 ID。
- 预期响应：当 `content_format=mermaid` 时，`content` 为可直接解析的 Mermaid 源码。
- 实际响应：`content` 包含 Markdown Mermaid 代码围栏及 `<!-- ... -->` 注释。
- 浏览器报错：修复前显示 `Syntax error in text, mermaid version 11.16.0`。
- 复现步骤：生成 mind_map；获取资源详情；把 `content` 直接交给 `mermaid.render`。
- 当前兼容：前端已清洗后渲染；建议后端统一输出纯 Mermaid 源码并增加 Reviewer 校验。

原 BE-001（可选 Agent2 包缺失导致 `develop` 无法启动）已随合并请求 #3 解决，本轮后端 48 项回归通过。

## 7. 当前风险与结论

- 最终演示环境必须配置真实 LLM 密钥，并再次确认页面显示 `llm_structured`，不能展示为开发适配器结果。
- Python 资源的偶发非法字符会影响“代码可运行”演示，应由资源 Agent 负责人优先修复并补语法回归。
- 前端主要 bundle 较大，但当前本地演示加载稳定，优先级低于真实 LLM 和资源质量。

结论：Day 2 的真实接口、五类资源渲染、多智能体进度和 mock 清理目标已完成；核心页面闭环可演示，
进入 Day 3 前应先关闭 BE-003，并用真实 LLM 配置跑一遍完整案例。
