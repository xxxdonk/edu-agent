# EduAgent 测试报告

报告日期：2026-07-16

集成分支：`agent1/integration`

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
| 后端测试 | `.\.venv\Scripts\python.exe -m pytest -q` | 93 passed |
| 前端测试 | `cd frontend; npm test -- --run` | 18/18 passed |
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
| Planner | `llm_structured`，初始 6 步，评价后 7 步 |
| 五类资源 | 5/5 成功 |
| RAG | 5 类资源均有真实课程来源 |
| Reviewer | 5/5 `approved` |
| Task | `completed` |
| SSE | 35 个业务事件，sequence 连续至 35 |
| Evaluation | 50%，故意错答 2 题，正确识别薄弱点 |
| 画像更新 | v1 → v2，证据来源为 `evaluation` |
| 路径更新 | 重新规划成功，包含 `adjustment_reason` |
| 缓存复跑 | 五类资源 5/5 命中，ID 全部重新绑定并再次审校 |

## 4. 性能基线与封版实测

完整真实流程约 87.6 秒：

| 阶段 | 耗时 |
|---|---:|
| 健康检查 | 24.0 ms |
| Profile | 25,314.9 ms |
| Planner | 13,111.8 ms |
| 五资源生成与 SSE | 22,144.6 ms |
| 资源查询校验 | 36.7 ms |
| Evaluation 与重规划 | 26,978.7 ms |
| 更新后画像查询 | 33.5 ms |

该数据是启用真实模型且缓存未作为基线加速条件时的单次结果。封版实测分别记录冷缓存和相同键缓存命中的耗时，不把命中结果误写为模型重新生成速度。

第五阶段最终冷缓存闭环的阶段计时为：

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

1. Quiz 固定三题、四选一标签归一化和不安全格式拒绝。
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

## 8. 三个固定演示案例

案例定义位于 `scripts/demo_cases.json`，验证器为 `scripts/verify_demo_cases.py`：

| 案例 | 画像级别 | 实际路径主题 | Quiz 得分 | 成功尝试 |
|---|---|---|---:|---:|
| A. 初学视觉型 | beginner | 向量与矩阵、梯度下降、线性回归、逻辑回归与分类、模型评估 | 0% | 1/1 |
| B. 考试型 | intermediate | 模型评估、过拟合、正则化、综合实战 | 66.67% | 第 2 次 |
| C. 项目实践型 | intermediate | 逻辑回归、模型选择、参数调优、项目实践、结果报告 | 16.67% | 第 3 次 |

三个案例的画像、路径和资源摘要指纹均不同；每个成功案例都是 Profile/Planner `llm_structured`、五资源 5/5、Reviewer 5/5、无资源 fallback、画像 v1→v2、路径重新规划并包含 `adjustment_reason`。B 的首次尝试未覆盖考试目标，C 的前两次分别出现知识级别不匹配和 Planner 降级；验证脚本如实记录案例级尝试次数和此前失败码，没有把失败覆盖为成功。

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

- 真实模型响应时间和结构遵循度受外部服务影响；本次 B、C 案例需要透明重试。
- 资源缓存是单进程内存缓存，服务重启或多进程部署时不共享。
- Profile、Planner 和三个私有 Draft 资源 Agent 仅在结构错误时最多请求一次格式修复；第二次失败仍显式 fallback，演示时必须关注模式和资源标记。
- 大型前端 chunk 警告不影响当前单机演示，但未来生产发布可继续拆分。
- OpenAPI 为 Evaluation 保留 501 声明以维持冻结契约；当前正常路径已返回真实结果。
