# EduAgent 测试报告

报告日期：2026-07-19

当前增强分支：`agent/content-depth-final`（基于 `develop@1636737`）

公共契约：`api-contract-v0.1`

## 1. 测试环境

| 项目 | 版本或地址 |
|---|---|
| Windows | 本地封版环境 |
| Python | 3.13.5 |
| Node.js | 24.18.0 |
| npm | 11.16.0 |
| 前端 | `http://127.0.0.1:5173/` |
| 后端 | `http://127.0.0.1:8000/` |
| 运行时模型 | DeepSeek，OpenAI 兼容协议 |
| 数据库 | SQLite |

## 2. 最终封版回归

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `.\.venv\Scripts\python.exe -m pytest -q` | 109 passed |
| 前端测试 | `cd frontend; npm test -- --run` | 24/24 passed |
| TypeScript 与生产构建 | `cd frontend; npm run build` | 通过，3385 个模块转换 |
| 公共 OpenAPI 与 Schema | 后端契约测试 | 无变化 |

唯一后端提示是 Starlette/httpx 的第三方弃用警告。生产构建存在第三方 PURE 注释和主包 chunk 较大的非阻断警告，不影响当前演示。

第四阶段基线为后端 65 项、前端 18 项。第五阶段增加了资源私有 Draft、受控的一次格式修复、进程内缓存、三个固定案例和交付检查；所有新增自动测试均不访问真实网络。

## 3. 最终真实端到端结果

验收输入覆盖：

- 人工智能专业大二
- 机器学习课程
- 数学基础一般
- 梯度下降薄弱
- 完成分类项目
- 偏好代码案例和图示
- 每天 45 分钟

结果：

| 阶段 | 结果 |
|---|---|
| Profile | `llm_structured`，画像字段与输入一致 |
| Planner | `llm_structured`，初始 3 步，评价后 4 步 |
| 五类资源 | 5/5 成功 |
| RAG | 5 类资源均有真实课程来源 |
| Reviewer | 5/5 `approved` |
| Task | `completed` |
| SSE | 35 个业务事件，sequence 连续至 35 |
| Evaluation | 50%，故意错答 2 题，正确识别薄弱点 |
| 画像更新 | v1 → v2，证据来源为 `evaluation` |
| 路径更新 | 重新规划成功，包含 `adjustment_reason` |
| 缓存 | 本轮为冷链路，0 命中；缓存命中与失效专项自动测试通过 |

## 4. 性能基线与封版实测

2026-07-17 当前完整真实流程约 112.5 秒：

| 阶段 | 耗时 |
|---|---:|
| 健康检查 | 9.6 ms |
| Profile | 20,881.3 ms |
| Planner | 18,671.4 ms |
| 五资源生成与 SSE | 17,948.2 ms |
| 资源查询校验 | 53.4 ms |
| Evaluation 与重规划 | 51,569.3 ms |
| 更新后画像查询 | 38.4 ms |

该数据是启用真实模型且缓存未作为基线加速条件时的单次结果。封版实测分别记录冷缓存和相同键缓存命中的耗时，不把命中结果误写为模型重新生成速度。

以下为此前第五阶段带 `--verify-cache` 的封版实测，用于保留缓存性能基线：

| 阶段 | 耗时 |
|---|---:|
| 健康检查 | 9.9 ms |
| Profile | 34,824.0 ms |
| Planner | 18,591.0 ms |
| 五资源生成与 SSE | 24,195.2 ms |
| 资源查询校验 | 33.1 ms |
| 相同键五资源缓存复跑 | 752.9 ms |
| Evaluation 与重规划 | 39,659.0 ms |
| 更新后画像查询 | 57.3 ms |

不含缓存复跑的冷链路阶段合计约 117.37 秒；包含缓存验证约 118.12 秒。该次总耗时高于 87.6 秒基线，主要来自 Profile 的一次格式修复和外部模型响应波动，不能把它描述为全链路提速。可复用资源阶段从 24.20 秒降至 0.75 秒，约减少 96.9%，且命中后仍重绑 ID、执行 Reviewer、持久化并发送完整 SSE。

## 5. 浏览器验收

使用真实后端和前端完成自动浏览器检查：

- 输入框为空时，助手消息自动完整显示。
- 五类资源卡片全部展示。
- Markdown、Mermaid、Quiz、Reading 和 Python 内容正常渲染。
- 标题、类型、目标主题、难度、个性化原因、来源和审校状态可见。
- Quiz 提交后显示评价结果。
- 画像更新到 v2，路径显示调整结果。
- 浏览器控制台错误 0、警告 0。
- Windows 一键启动脚本实测前后端均就绪；触发退出后 8000、5173 端口均释放，没有遗留 Vite 子进程。

## 6. 第五阶段自动测试范围

封版回归覆盖：

1. Quiz 分层题目、四选一标签归一化和不安全格式拒绝；当前内容增强版默认 9 题。
2. MindMap 外层围栏归一化、`mindmap` 正文和语法约束。
3. Reading 固定段落结构与三个核心要点。
4. 明确格式错误只允许一次修复请求。
5. 第二次失败后显式 development fallback。
6. 五资源仍真实并行，单项失败仍为 `partial_success`。
7. Reviewer 对每个成功资源执行且拒绝项不发布。
8. 缓存键包含画像、路径、类型、模型、知识库和生成器版本。
9. 画像或知识库变化时不命中旧缓存。
10. `regenerate=true` 失效对应键。
11. 缓存命中仍生成新资源 ID、重写 Quiz 题目 ID 并重新审校。
12. 缓存不保存 fallback 或未审校通过资源。
13. SSE 顺序、恢复、终态和缓存命中事件。
14. Evaluation 真实评分、画像版本递增和路径调整。
15. OpenAPI 9 个操作和公共 Schema 指纹不变。

自动测试使用 Fake LLM 和临时数据库，不访问真实网络。

## 7. 三个资源 Agent 连续真实验证

`verify_resource_stability.py --runs 3` 强制 `regenerate=true`，三次任务均为 `completed`，不使用资源缓存：

| Agent | LLM 成功 | fallback | Reviewer approved |
|---|---:|---:|---:|
| Quiz | 3/3（100%） | 0 | 3/3 |
| Reading | 3/3（100%） | 0 | 3/3 |
| MindMap | 3/3（100%） | 0 | 3/3 |

三次资源任务分别耗时 17.91 秒、13.58 秒和 13.52 秒。显式 fallback 机制仍保留，但本轮连续验证没有触发。

## 8. 三个固定演示案例（此前封版实测）

案例定义位于 `scripts/demo_cases.json`，验证器为 `scripts/verify_demo_cases.py`：

| 案例 | 本轮状态 | Profile / 初始 Planner | 五资源 / Reviewer | 评价后 Planner |
|---|---|---|---|---|
| A. 初学视觉型 | 首次成功 | `llm_structured` / `llm_structured` | 5/5 / 5/5 approved | `llm_structured` |
| B. 考试型 | 透明重试后成功 | `llm_structured` / `llm_structured` | 5/5 / 5/5 approved | `llm_structured` |
| C. 项目实践型 | 两次内未通过严格验收 | `llm_structured` / `llm_structured` | 5/5 / 5/5 approved | `development_rule_based` |

该表是当前无人值守回归之前的历史封版实测。A、B 完成画像 v1→v2、真实评价和带 `adjustment_reason` 的重规划；C 当时在评价后 Planner 阶段显式降级，验证器没有把 fallback 写成成功。后续 Planner 专项修复已取得案例 C 三次连续 `llm_structured`，最新轻量回归见第 13 节。

验证器为每次尝试创建唯一学生 ID，并比较画像、路径主题、资源个性化摘要和评价后变化。脚本只输出安全摘要，不输出 API Key、完整输入或完整模型响应。

## 9. 真实验证命令

先启动前后端，再在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_llm_profile_planner.py
.\.venv\Scripts\python.exe .\scripts\verify_end_to_end.py --verify-cache
.\.venv\Scripts\python.exe .\scripts\verify_resource_stability.py --runs 3
.\.venv\Scripts\python.exe .\scripts\verify_demo_cases.py
```

真实模型验证不是 pytest 的一部分，需要本机 `.env` 和可用网络。脚本只输出供应商、模型、模式、计数、状态、脱敏摘要和耗时。

## 10. 已知非阻断风险

- 真实模型响应时间和结构遵循度受外部服务影响；录制前必须以新的学生 ID 重新预检，不复用历史成功结果。
- 资源缓存是单进程内存缓存，服务重启或多进程部署时不共享。
- Profile、Planner 和三个私有 Draft 资源 Agent 仅在结构错误时最多请求一次格式修复；第二次失败仍显式 fallback，演示时必须关注模式和资源标记。
- 大型前端 chunk 警告不影响当前单机演示，但未来生产发布可继续拆分。
- OpenAPI 为 Evaluation 保留 501 声明以维持冻结契约；当前正常路径已返回真实结果。

## 11. Agent 3 本机跟进回归

跟进日期：2026-07-16
本机基线：`develop@aba8875`
本地工作分支：`agent/frontend-day3-followup`

| 检查 | 本机结果 |
|---|---|
| 后端测试（当时基线） | 93 passed，1 条 Starlette/httpx 依赖弃用警告 |
| 前端测试 | 24 passed（第三天修改后） |
| TypeScript 与生产构建 | 通过，3385 个模块转换 |
| 健康检查 | 后端与数据库均为 `ok` |
| 浏览器闭环 | 5 类资源、35 条 SSE、Mermaid SVG、3 题评价、画像 v1→v2、路径 2→3 步 |
| 桌面布局 | `1440x1000` 下 `documentWidth=1425`，无横向溢出 |
| 移动端布局 | `390x844` 下页面宽度 390，无横向溢出或越界元素 |

本机没有真实模型配置，仅创建了由 `.env.example` 复制且不含密钥的本地 `.env`。
因此本轮浏览器回归明确使用 development fallback；未重新声称三个真实 LLM 案例通过，
真实案例结果仍以本报告前述封版环境记录为准。

### BE-005：fallback 评价摘要产生带前缀残片的薄弱知识点

- 接口地址：`POST /api/evaluation/submit`
- 请求参数：3 题 Quiz 的 `EvaluationSubmission`，其中两道主观题回答“不了解，需要继续复习”。
- 预期响应：画像薄弱点保持规范主题，例如“梯度下降”，更新路径使用同一规范主题。
- 实际响应：画像 v2 新增“点：了解Python但梯度下降”，路径步骤也出现该带前缀残片的主题。
- 浏览器报错：无 JavaScript 异常；画像和路径前后对比可见异常文本。
- 复现步骤：在未配置 LLM 的环境启动系统；输入包含梯度下降薄弱点的画像描述；生成 Quiz；提交低分答案；查看画像与路径更新前后对比。
- 当前处理：已在 Profile 私有 Draft、启发式提取和画像合并边界清理明确标签，并保留原始 `source=evaluation` 摘要；公共 StudentProfile Schema 不变。无网络测试覆盖前缀、去重、普通中文冒号、v1→v2 和证据保留。

### FE-003：资源来源标题重复影响演示可读性

同一课程章节的多个检索 chunk 会返回相同 `title`。资源详情此前直接拼接标题，出现
“线性回归、线性回归、线性回归”等重复文本。本轮仅在展示层按标题去重，完整 locator、
chunk ID 和来源行仍保留在折叠面板中，不改变接口数据或溯源信息。

## 12. 第三天学习评价回归

跟进日期：2026-07-17

| 检查 | 本机结果 |
|---|---|
| 每题评价状态 | 1 道正确显示绿色，2 道错误显示红色 |
| 评价信息 | 总分、逐题结果、参考答案、解析、薄弱知识点和学习建议均可见 |
| 动态闭环 | 画像 v1→v2，路径 2→3 步，前后差异均可见 |
| 浏览器闭环 | 5 类资源、35 条持久化 SSE、Mermaid SVG、3 题评价通过 |
| 移动端评价区 | `390x844` 下页面宽度 390，无横向溢出或越界元素 |
| 前端自动化 | 3 个测试文件，24 tests passed |
| TypeScript 与生产构建 | 通过，3385 个模块转换 |

### FE-004：错误答案被误用正确状态样式

后端反馈“回答不正确”包含“正确”二字，旧逻辑使用 `includes('正确')` 判断，导致错误答案也套用绿色正确样式。本轮改为解析完整题目反馈前缀，明确区分 `correct`、`partial`、`incorrect` 和 `unknown`，并增加回归测试。

### 三案例本机状态

`scripts/demo_cases.json` 已包含初学视觉型、考试型和项目实践型三个案例。运行 `verify_demo_cases.py` 时，本机在请求前按预期停止并返回 `real_llm_configuration_missing`；当前 `.env` 没有 `LLM_MODEL`、`LLM_BASE_URL` 和 `LLM_API_KEY`。因此本轮只确认 development fallback 浏览器闭环，不把它表述为三个真实 LLM 案例通过。

## 13. 无人值守最终回归

最终自动回归结果：

| 检查 | 结果 |
|---|---|
| 后端 | 109 passed，1 条既有 Starlette/httpx 弃用警告 |
| 前端 | 3 个测试文件，24/24 passed |
| TypeScript / Vite | 通过，保留非阻断的大 chunk 警告 |
| Planner 案例 C 专项 | 三次连续评价后 `llm_structured`，0 fallback |
| Profile weak_topics | 明确前缀清理、重复值去重、evaluation 原始证据保留 |
| 演示预检 | 20/20 PASS，0 WARN，0 FAIL |
| 公共契约 | OpenAPI 与公共 Schema 指纹不变 |

本轮轻量真实验证严格限制每个案例最多一次透明重试，且资源请求使用 `regenerate=true`，缓存命中为 0：

- 案例 B：两次内未完成严格闭环。第一次在路径语义验收后、资源任务前停止；第二次为 `knowledge_level_mismatch`。没有 fallback 或格式修复日志。
- 案例 C：两次均完成五资源与评价后重规划，Planner 均为 `llm_structured`，五资源 5/5、Reviewer 5/5、`adjustment_reason` 存在；验证器最终发现重复 weak topic 场景漏合并 evaluation evidence。该内部合并根因随后已修复并由无网络测试验证，遵守调用上限未追加第三次真实请求。

真实冷链路可能超过两分钟；DeepSeek 的字段证据和语义遵循度仍有波动。内容增强版正式录制推荐案例 C，案例 B 作为考试场景备用；两者都必须在录制前用新学生 ID 预检。任何 development fallback 都必须原样展示，不能作为真实模型成功。

## 14. 内容丰富度与演示深度增强回归

本轮不修改公共 API、公共 Schema、数据库结构、依赖和资源类型。增强内容包括：

- Explanation：12 段课程结构、闭合 KaTeX 公式、4 条以上常见错误、3 个自检问题和 5 组 FAQ。
- Mind Map：12 至 24 个简短节点，覆盖定义、前置、原理、流程、错误、项目与 Evaluation。
- Quiz：9 题默认输出，覆盖 3 道基础单选、3 道进阶简答和 3 道项目综合题。
- Reading：快速/深入阅读、项目路线、10 个术语、6 个检查问题和真实 RAG 来源。
- Coding：仅依赖 Python 标准库的客户流失分类实验，含预期输出、TODO、调试、挑战和反思。
- Reviewer：增加五类资源的结构、数量、重复、语法和危险内容质量门槛。
- 前端：资源包总览、个性化依据、只填入不发送的追问建议、Quiz 导航/进度/未答提示/重复提交保护。

| 检查 | 本轮结果 |
|---|---|
| 后端测试 | 152 passed，1 条既有 Starlette/httpx 弃用警告 |
| 前端测试 | 65 passed |
| TypeScript 与 Vite build | 通过，3391 个模块转换 |
| 演示预检 | 18 PASS / 2 FAIL；本机缺少 `LLM_MODEL` 与 `LLM_API_KEY` |
| 公共 API / Schema / 数据库 | 无变化 |
| 新增依赖 / 新资源类型 | 均无 |

自动测试不访问真实网络。本机未配置可用于验收的真实模型密钥，因此没有追加案例 C 的真实 LLM 调用；正式录制前仍需使用一个新的 `student_id` 按本报告命令完成一次冷链路，fallback 必须如实展示。
