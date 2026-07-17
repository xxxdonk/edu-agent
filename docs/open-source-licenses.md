# EduAgent 开源软件与许可证记录

以下信息来自本仓库锁定依赖的包元数据。最终提交前应随 `package-lock.json` 和 Python requirements 再次核对。

## 前端

| 名称 | 用途 | 来源 | 许可证 |
|---|---|---|---|
| Vue 3 | 视图框架 | npm `vue` | MIT |
| Vite | 开发与生产构建 | npm `vite` | MIT |
| TypeScript | 静态类型检查 | npm `typescript` | Apache-2.0 |
| Element Plus | UI 组件与图标 | npm `element-plus`、`@element-plus/icons-vue` | MIT |
| Pinia | 前端状态管理 | npm `pinia` | MIT |
| Axios | REST 请求 | npm `axios` | MIT |
| Mermaid | 思维导图渲染 | npm `mermaid` | MIT |
| markdown-it | Markdown 渲染 | npm `markdown-it` | MIT |
| highlight.js | Python 与代码高亮 | npm `highlight.js` | BSD-3-Clause |
| Vitest | 前端单元测试 | npm `vitest` | MIT |
| Vue Router | 前端路由基础 | npm `vue-router` | MIT |

## 后端

| 名称 | 用途 | 来源 | 许可证 |
|---|---|---|---|
| FastAPI | HTTP API | PyPI `fastapi` | MIT |
| Uvicorn | ASGI 服务 | PyPI `uvicorn` | BSD-3-Clause |
| Pydantic | 公共 schema 校验 | PyPI `pydantic` | MIT |
| HTTPX | HTTP 客户端与测试 | PyPI `httpx` | BSD-3-Clause |
| Pytest | 后端测试 | PyPI `pytest` | MIT |

## 数据与 AI 工具

- 课程知识库：仓库自建的《机器学习基础》课程大纲与来源清单，位置为 `data/machine_learning/`。
- 大模型：通过 OpenAI 兼容协议接入，实际供应商和模型名称由最终演示环境 `.env` 配置，提交材料中应记录具体模型与服务条款。
- AI 编码工具使用说明见 `docs/ai-coding-tool-statement.md`。
