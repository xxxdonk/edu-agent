# A3中国软件杯项目全局规则

## 项目信息

项目名称：EduAgent——基于动态学习画像的多智能体个性化学习资源生成系统

赛题：基于大模型的个性化资源生成与学习多智能体系统开发

团队人数：3人

剩余时间：5天

默认演示课程：《机器学习基础》

## 项目核心目标

实现以下完整闭环：

自然语言学习对话
→ 动态学生画像
→ 个性化学习路径
→ 多智能体协同生成至少5类学习资源
→ 内容审校
→ 学习练习与评价
→ 更新学生画像
→ 动态调整学习路径

## 强制功能

1. 通过自然语言对话构建画像，不能使用传统问卷作为主要方式。
2. 学习画像不少于6个维度，并支持动态更新。
3. 系统必须体现真实多智能体协作和状态传递。
4. 至少生成5种个性化资源：
   - 课程讲解文档
   - 思维导图
   - 分层练习题
   - 拓展阅读
   - 代码实践案例
5. 根据画像生成有先后顺序的学习路径。
6. 所有资源应与学生专业、水平、目标、薄弱点和偏好相关。
7. 资源生成必须基于课程知识库，并展示来源。
8. 必须具有内容安全和幻觉防范机制。
9. 核心生成过程应提供进度事件或流式展示。
10. 项目必须可在普通开发环境中稳定运行。

## 智能体

- Orchestrator Agent：工作流编排
- Profile Agent：学习画像提取与更新
- Planner Agent：学习路径规划
- Explanation Agent：讲解文档生成
- MindMap Agent：思维导图生成
- Quiz Agent：练习生成
- Reading Agent：拓展阅读生成
- Coding Agent：代码案例生成
- Reviewer Agent：内容审校
- Evaluation Agent：学习效果分析

## 统一数据契约

公共模型命名以 `backend/app/schemas` 的实际代码为唯一标准：

- `Resource`：学习资源实体。
- `TaskState`：资源生成任务状态实体。

Agent 2和Agent 3不得重复创建 `LearningResource`、`GenerationTask` 等同义模型；如产品文案使用“学习资源”或“生成任务”，仍必须映射到 `Resource`、`TaskState` 公共契约。

学生画像至少包含：

- major
- course
- knowledge_level
- learning_goals
- weak_topics
- learning_history
- cognitive_style
- language_preference
- resource_preference
- time_budget
- evidence
- confidence
- updated_at

资源输出必须包含：

- resource_id
- resource_type
- title
- content
- target_topic
- difficulty
- personalization_reason
- source_references
- review_status
- created_at

学习路径步骤必须包含：

- step
- topic
- learning_goal
- reason
- recommended_resources
- completion_criteria
- estimated_minutes
- prerequisites

## 代码边界

Agent 1主要修改：

- backend/app/api
- backend/app/orchestrator
- backend/app/profile
- backend/app/planner
- backend/app/schemas
- backend/app/database
- docs/architecture.md
- docs/api-spec.md

Agent 2主要修改：

- backend/app/rag
- backend/app/resources
- backend/app/guardrails
- backend/app/evaluation
- data
- backend/tests

Agent 3主要修改：

- frontend
- docs/user-guide.md
- docs/test-report.md
- docs/demo-script.md
- PPT和视频材料

未经说明不得大规模修改其他成员目录。

## 开发规则

1. 不直接向main提交代码。
2. 公共契约由docs/api-spec.md和schemas定义。
3. 修改接口时必须同步更新文档。
4. 不得以固定返回值冒充真实生成结果。
5. 临时mock必须明确标记，并在第2天结束前替换。
6. 不得删除功能来绕过错误。
7. 所有大模型返回必须经过结构校验。
8. 所有关键功能必须有测试样例。
9. 不得引入与评分无关的复杂架构。
10. 每次任务完成后必须报告修改文件、测试结果和遗留问题。
11. 所有开源框架、模型、数据及AI工具必须记录名称、来源和协议。
12. 生成内容应附带知识库来源，缺少可靠依据时应明确表示无法确认。
13. 不得在代码中提交API密钥。
14. 必须提供.env.example。
15. 最终运行不能依赖开发者手动修改源代码。

## 优先级

P0：画像、多智能体、5类资源、路径、知识库、运行和提交材料。

P1：答题评价、画像更新、路径更新、智能体轨迹、内容审校。

P2：智能辅导、语音、视频、登录和后台。

必须先完成P0，再完成P1，不得提前开发P2。

## 每次回复格式

1. 已理解的任务
2. 修改文件
3. 完成内容
4. 运行命令
5. 测试命令及结果
6. 当前是否存在mock
7. 未完成问题
8. 对其他成员的依赖
9. 下一步最优先任务
