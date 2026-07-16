# EduAgent 开源软件、模型服务与课程来源

本记录依据仓库中的 `backend/requirements.txt`、`backend/requirements-dev.txt`、`frontend/package.json` 和 `frontend/package-lock.json` 整理。依赖包自身的许可证文本和锁文件是最终核对依据。

## 1. 前端直接依赖

| 名称 | 用途 | 许可证 |
|---|---|---|
| Vue 3 | 视图框架 | MIT |
| Vue Router | 路由 | MIT |
| Pinia | 状态管理 | MIT |
| Element Plus | UI 组件 | MIT |
| Element Plus Icons | 图标 | MIT |
| Axios | HTTP 客户端 | MIT |
| Mermaid | 思维导图渲染 | MIT |
| markdown-it | Markdown 渲染 | MIT |
| highlight.js | 代码高亮 | BSD-3-Clause |

## 2. 前端开发依赖

| 名称 | 用途 | 许可证 |
|---|---|---|
| Vite | 开发服务器与构建 | MIT |
| `@vitejs/plugin-vue` | Vue 单文件组件构建 | MIT |
| TypeScript | 静态类型检查 | Apache-2.0 |
| Vitest | 前端单元测试 | MIT |
| `vue-tsc` | Vue TypeScript 检查 | MIT |
| `@types/node` | Node.js 类型定义 | MIT |
| `@types/markdown-it` | markdown-it 类型定义 | MIT |

## 3. 后端直接依赖

| 名称 | 用途 | 许可证 |
|---|---|---|
| FastAPI | HTTP API | MIT |
| Uvicorn | ASGI 服务 | BSD-3-Clause |
| Pydantic | 公共 Schema 与私有 Draft 校验 | MIT |
| HTTPX | 模型 HTTP 客户端与测试 | BSD-3-Clause |
| python-dotenv | 根目录 `.env` 加载 | BSD-3-Clause |
| pytest | 后端自动测试 | MIT |

Uvicorn 和前端依赖还会安装锁文件记录的传递依赖。发布时应保留各包随附的许可证声明，不把本文件当作上游许可证文本的替代品。

## 4. DeepSeek 模型服务

EduAgent 通过 OpenAI 兼容协议调用 DeepSeek。模型地址、模型名称和授权凭证由运行环境提供，不写入仓库。

DeepSeek 是外部模型服务，不属于本仓库的开源依赖，也不因本项目许可证而获得再授权。实际演示和部署应遵守模型服务提供方当时适用的服务条款、隐私规则和内容规范。

系统对 DeepSeek 输出执行：

- 私有 Draft 校验；
- 事实与来源约束；
- 公共 Pydantic Schema 校验；
- Reviewer 审校；
- 明确的格式修复与 development fallback 标记。

## 5. Codex 开发工具

OpenAI Codex 用于本项目开发期间的代码审计、实现协作、测试、文档整理和回归验证。Codex 不作为 EduAgent 运行时 Agent，也不参与学生画像或学习评价的线上决策。

详细的人机分工、复核和责任边界见 `docs/ai-coding-tool-statement.md`。

## 6. 课程知识库

仓库中的课程知识库位于 `data/machine_learning/`，包括：

- 自建《机器学习基础》课程大纲；
- 8 个课程章节学习笔记；
- `sources.json` 参考来源索引；
- 章节中的 AIGC 来源标识和保留元数据。

这些文件是为课程检索整理的摘要、教学笔记和定位信息，不包含下列教材或课程的完整原文：

| 参考来源 | 作者或课程方 | 用途 |
|---|---|---|
| 《机器学习》 | 周志华 | 机器学习概念、经典算法和理论框架 |
| 《统计学习方法》 | 李航 | 统计学习方法和数学推导 |
| Machine Learning | Andrew Ng / Coursera | 直观入门与实践思路 |
| Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow | Aurélien Géron | Python 项目与工程实践参考 |
| Deep Learning | Ian Goodfellow、Yoshua Bengio、Aaron Courville | 神经网络与深度学习理论参考 |

上述书名、课程名和相关内容权利归原作者及权利人所有。EduAgent 的 `source_references` 指向仓库内课程笔记或来源索引，不能被解释为对原作全文的再分发或对外部资料版权的授权。

## 7. 项目自产内容

以下属于本仓库项目实现或整理内容：

- 公共 API 与 Schema；
- Agent 编排、缓存、SSE 和 Evaluation 实现；
- Vue 学习工作台；
- 自动测试和验证脚本；
- 课程大纲、章节摘要、演示案例和项目文档。

提交前应同时检查竞赛规则、仓库根许可证文件及所有第三方依赖随附声明。若最终提交包增加新的第三方代码或素材，应在本记录中补充其名称、用途、来源和许可证。
