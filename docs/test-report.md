# EduAgent 前端与集成测试报告

测试日期：2026-07-15

测试分支：`agent/frontend-core-workspaces`

前端基线：`develop@cba7100`

资源集成验证：`origin/Agent2@9b498f0`

## 1. 测试环境

| 项目 | 版本 |
|---|---|
| Windows | 本地开发环境 |
| Python | 3.13.3 |
| Node.js | 24.15.0 |
| npm | 11.12.1 |
| 前端地址 | `http://127.0.0.1:5173/` |
| 后端地址 | `http://127.0.0.1:8000/` |

## 2. 自动化结果

| 检查 | 命令 | 结果 |
|---|---|---|
| TypeScript + 生产构建 | `cd frontend; npm run build` | 通过，3385 模块完成转换 |
| 前端单元测试 | `cd frontend; npm test` | 1 个文件、2 个测试全部通过 |
| `develop` 后端回归 | `cd backend; ..\.venv\Scripts\python.exe -m pytest -q` | 30 通过、1 失败、6 错误 |
| Agent2 后端回归 | 在 Agent2 临时工作树运行同一命令 | 37 通过，1 条依赖弃用警告 |

生产构建存在 Mermaid 与主包 chunk 大于 500 kB 的非阻断警告。Mermaid 已采用动态导入，首屏无需加载全部图表实现；比赛演示局域环境不受影响，后续可继续按资源类型拆包。

## 3. 真实接口端到端验证

在 Agent2 独立工作树启动后端，不修改本前端分支的后端代码。测试输入为计算机专业、机器学习入门、梯度下降薄弱、偏好中文和代码实践、每天 45 分钟的自然语言描述。

| 验证项 | 实际结果 | 状态 |
|---|---|---|
| `GET /api/health` | 服务与数据库均为 `ok` | 通过 |
| `POST /api/profile/chat` | 生成 v1、10 维画像 | 通过 |
| 画像生成模式 | `development_heuristic`，前端明确标记 | 通过 |
| `POST /api/path/generate` | 生成 2 个有序步骤 | 通过 |
| 路径生成模式 | `development_rule_based`，前端明确标记 | 通过 |
| `POST /api/resources/generate` | 创建异步任务并到达 `completed` | 通过 |
| SSE | 返回 15 条 data 事件，前端按 sequence 去重 | 通过 |
| 五类资源 | explanation、mind_map、quiz、reading、coding 各 1 项 | 通过 |
| Reviewer | 5 项均为 `approved` | 通过 |
| `POST /api/evaluation/submit` | `mastery_score=1.0`、`passed=true` | 通过 |

## 4. 页面与交互状态

已验证：初始状态、画像加载、路径加载、Agent 生成中、成功、部分成功、全部失败、空结果、网络错误、30 秒 REST 超时、后端异常、Mermaid 渲染失败、SSE 三次续传、轮询兜底和重试生成。

使用 Edge Headless 在 `1440×1000` 视口检查首屏，品牌区、流程导航、三工作区标签、聊天区、画像空态和健康状态无重叠。通过 DevTools 设备指标在 `390×844` 视口复核：`documentWidth=390`、`bodyWidth=390`，未发现超出视口元素。当前前端服务返回 HTTP 200。

## 5. 已发现后端问题

### BE-001：develop 分支无法在缺少 Agent2 包时启动

- 接口地址：`GET /api/health`（应用启动阶段即失败）
- 请求参数：无
- 预期响应：HTTP 200，返回 `HealthResponse`
- 实际响应：Uvicorn/TestClient 启动失败，`ModuleNotFoundError: No module named 'app.resources'`
- 浏览器报错：无法连接学习服务
- 复现步骤：检出 `develop@cba7100`；安装 `backend/requirements-dev.txt`；进入 `backend`；运行 pytest 或启动 Uvicorn
- 初步定位：`backend/app/orchestrator/bootstrap.py` 对 `importlib.util.find_spec('app.resources.registry')` 的调用在父包不存在时没有捕获 `ModuleNotFoundError`
- 处理状态：未修改后端；待系统集成负责人合并 Agent2 或修复可选模块检测

### BE-002：Evaluation Agent 未直接持久化画像与路径更新

- 接口地址：`POST /api/evaluation/submit`
- 请求参数：`EvaluationSubmission`
- 预期响应：返回 `EvaluationResult`，并按 API 文档触发画像版本和路径更新
- 实际响应：返回评价及两个 update_required 标志，但 Agent2 实现未直接调用 Profile/Planner 持久化更新
- 浏览器表现：评价成功，但必须由前端补充调用 `/api/profile/chat` 和 `/api/path/generate`
- 复现步骤：生成 quiz；提交错误答案；检查评价响应及数据库中的画像/路径版本
- 当前兼容：前端根据 update_required 标志完成后续两次真实调用，并展示前后对比
- 风险：若团队决定后端内部完成闭环，需要约定避免前后端重复更新

## 6. 遗留风险

- `Agent2` 尚未合入 `develop`，当前 `develop` 无法完成五资源与评价演示。
- 真实 LLM 尚未在本次环境配置，画像和路径验证结果是明确标记的开发适配器结果。
- 尚需在最终集成分支执行完整人工点击回归，并录制最终演示视频。
