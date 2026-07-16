# EduAgent 需求与验收范围

## 1. 产品目标

EduAgent 面向机器学习课程，根据学生自然语言描述和练习结果，持续生成可解释、可追溯的个性化学习路径与资源。

## 2. 核心功能

1. 使用自然语言对话建立学生画像。
2. 保存专业、课程、基础、目标、薄弱点、偏好和时间预算及其证据。
3. 根据真实画像生成无重复、带前置关系的学习路径。
4. 从本地课程知识库检索真实来源。
5. 并行生成讲解、思维导图、Quiz、阅读和代码五类资源。
6. Reviewer 对每个成功资源逐项审校。
7. 通过 SSE 展示可恢复的实时任务进度。
8. 前端展示成功资源，并隔离单项失败。
9. 根据持久化 Quiz 的真实答案计算评价。
10. 以 evaluation 证据更新画像版本并重新规划路径。

## 3. 非功能要求

- 公共 API、Schema、字段、枚举和五类资源类型冻结。
- 自动测试不访问真实网络。
- 真实模型失败时必须显式降级。
- 无真实课程来源时不得伪造引用。
- 单个 Agent 失败不得阻塞其他 Agent。
- SSE sequence 连续、支持恢复、终态关闭。
- API Key、完整模型响应和学生隐私不写日志或提交包。
- Windows 单机环境可一键和手动启动。
- 缓存不能跨画像、路径、模型或知识库版本误用。

## 4. 运行边界

当前版本支持：

- 单个 FastAPI 进程；
- SQLite；
- Vue 3 前端；
- DeepSeek OpenAI 兼容接口；
- 本地机器学习课程知识库；
- 单进程 TTL/LRU 资源缓存。

当前版本不包含：

- 登录注册；
- 管理员后台；
- 视频或语音生成；
- 多进程共享任务队列；
- 多租户权限系统。

## 5. 固定验收案例

基础端到端案例：

> 我是人工智能专业大二学生，目前在学习机器学习，数学基础一般，梯度下降一直没弄懂，希望完成一个分类项目。我每天可以学习45分钟，偏好代码案例和图示。

验收重点：

- Profile 和 Planner 为 `llm_structured`；
- 画像识别输入中的七类关键信息；
- 路径优先数学基础和梯度下降，并包含分类项目；
- 五类资源至少四类成功，目标为五类全部成功；
- 成功资源有真实来源并经过 Reviewer；
- SSE 到达任务终态；
- Evaluation 真实评分；
- 画像版本递增；
- 新路径包含 `adjustment_reason`；
- 公共契约不变化。

三个差异化演示案例定义在 `scripts/demo_cases.json`，讲解与预期见 `docs/demo-script.md`。

## 6. 质量门槛

提交前执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location .\frontend
npm test -- --run
npm run build
```

真实服务启动后执行：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_end_to_end.py --verify-cache
.\.venv\Scripts\python.exe .\scripts\verify_demo_cases.py
```

最终提交不得包含 `.env`、API Key、虚拟环境、node_modules、运行数据库、Python 缓存、dist、临时截图、日志、调试响应或个人绝对路径。
