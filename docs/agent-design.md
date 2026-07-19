# EduAgent Agent 设计

## 1. 设计原则

- 所有 Agent 复用 `backend/app/schemas` 中的公共对象。
- 模型只生成私有 Draft，业务层校验后映射到公共对象。
- 资源 Agent 共享同一画像和路径快照，不使用全局可变状态传递结果。
- 单个资源失败不取消其他资源。
- 所有降级、缓存命中和审校状态均可识别。

## 2. Agent 清单

| Agent | 输入 | 输出 | 关键校验 |
|---|---|---|---|
| Profile | 完整对话历史、旧画像、可选评价摘要 | `ProfileChatResponse` | 证据原文、来源、置信度、版本 |
| Planner | `StudentProfile`、旧路径、评价摘要 | `LearningPath` | 顺序、重复、前置关系、时间 |
| Retriever | 主题、难度、课程知识库 | 课程片段和 `SourceReference` | 真实文件、知识库版本 |
| Explanation | `SharedAgentContext`、RAG | explanation `Resource` | Markdown、来源、个性化 |
| MindMap | `SharedAgentContext`、RAG | mind_map `Resource` | Mermaid mindmap |
| Quiz | `SharedAgentContext`、RAG | quiz `Resource` | 三题、答案、解析、题目 ID |
| Reading | `SharedAgentContext`、RAG | reading `Resource` | 固定段落结构、来源 |
| Coding | `SharedAgentContext`、RAG | coding `Resource` | Python 基本语法、可运行性 |
| Reviewer | 单个生成资源、共享上下文 | 更新审校状态的 `Resource` | 事实、来源、格式、安全 |
| Evaluation | Quiz 提交、路径和持久化题目 | `EvaluationResult` | 归属、答案、薄弱点 |
| Orchestrator | 资源请求、画像、路径 | `TaskState`、事件和资源 ID | 并行、失败隔离、终态 |

五类资源和 Reviewer 由 `backend/app/resources/registry.py` 统一注册。

## 3. SharedAgentContext

资源阶段唯一共享上下文包含：

- `task_id`
- `ResourceGenerationRequest`
- 不可变 `StudentProfile` 快照
- 不可变 `LearningPath` 快照
- 内部事件回调

资源 Agent 不修改画像或路径。Evaluation 闭环由 API 层协调 Profile 和 Planner。

## 4. 结构化输出

Profile 和 Planner 使用结构化私有模型。Quiz、MindMap 和 Reading 使用更小的专用 Draft：

- Quiz：基础单选、进阶简答、挑战综合；
- MindMap：一个 Mermaid 内容字段；
- Reading：概览、三个核心要点、实践联系、后续学习。

Profile、Planner 和三个私有资源 Draft 的明确结构错误最多允许一次格式修复请求。资源修复不能新增来源或事实，画像证据仍必须可追溯，路径业务约束仍完整执行。第二次失败后使用显式 development fallback；安全、来源和 Reviewer 校验不放宽。

## 5. 资源生命周期

1. Retriever 返回真实课程片段。
2. 资源 Agent 生成公共 `Resource`，初始审校状态为 `pending`。
3. Reviewer 对每个成功资源单独审校。
4. `approved` 资源持久化并可写缓存。
5. `needs_revision` 资源持久化，但任务为 `partial_success`。
6. `rejected` 或审校异常的资源不发布为成功结果。

缓存命中资源会获得新 ID、恢复为 `pending` 并再次审校。development fallback 不写缓存。

## 6. Evaluation 闭环

Evaluation 只接受当前学生、路径步骤和持久化 Quiz 的题目 ID。评分后生成必要摘要，以 `evaluation` 证据更新画像，并调用 Planner 创建带 `adjustment_reason` 的新路径。评价内容不会伪装成用户对话。

## 7. 可观察性

- Profile/Planner 通过公开 mode 标识真实或降级。
- 资源 fallback 写入个性化原因和安全日志。
- 缓存命中写入 Retriever SSE 消息和安全日志。
- Agent、Reviewer 和任务终态写入连续 SSE 事件。
- 日志不输出 API Key 或完整模型响应。

## 8. 封版归一化与演示预检

Profile 的私有边界只移除 weak topic 开头的明确字段标签，不截断普通中文冒号内容。评价摘要原文继续作为 `source=evaluation` 证据保存；即使知识点值与旧画像重复，证据也会合并，版本仍按 v1→v2 递增。

Planner 的私有 Draft 固定字段并减少评价后输入，只接收画像摘要、未掌握主题、当前路径摘要和 adjustment reason。安全格式问题可归一化，核心学习内容缺失仍失败；一次修复后再次失败保持 `development_rule_based`，不会标为 `llm_structured`。

演示前由 `scripts/preflight_demo.py` 做无资源生成检查。一键启动脚本自动调用预检；真实模型冷链路可能超过两分钟。缓存为单进程 TTL/LRU，fallback 资源不进入缓存，所有模式和修复结果保持可观察。
