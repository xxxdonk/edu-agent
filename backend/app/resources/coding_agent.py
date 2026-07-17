from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty

from .base import BaseResourceAgent


class CodingAgent(BaseResourceAgent):
    agent_name = "coding_agent"
    resource_type = ResourceType.CODING

    async def _generate_with_llm(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        system_prompt = (
            "你是一位机器学习工程师。根据课程知识库，生成一份可运行的 Python 代码实践案例。"
            "必须包含：完整可运行代码、详细注释、预期输出和使用说明。"
            "难度与学生水平匹配，使用 sklearn / numpy 等常用库。"
            "代码格式为 Python，用 Markdown 包裹代码块。"
        )
        user_content = (
            f"主题：{topic}\n"
            f"学生水平：{difficulty}\n"
            f"学习历史：{context.profile.learning_history.value}\n"
            f"认知风格：{context.profile.cognitive_style.value}\n"
        )
        if rag_context:
            user_content += f"知识库参考：\n{rag_context}\n"
        user_content += "请生成一份完整的 Python 代码实践案例。"

        draft = await self._llm_client.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_content)],
            response_model=Resource,
        )
        return self._finalize(draft, topic, difficulty, references, context)

    def _generate_heuristic(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        level_labels = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}
        label = level_labels.get(difficulty, "入门")

        var_name = topic.lower().replace(" ", "_").replace("-", "_")
        content = (
            f"# {topic} — Python 代码实践（{label}）\n\n"
            f"## 目标\n"
            f"通过本案例理解 {topic} 的核心实现，掌握相关 API 的使用方法。\n\n"
            f"## 环境要求\n"
            f"- Python 3.8+\n"
            f"- numpy\n"
            f"- scikit-learn\n\n"
            f"## 代码实现\n\n"
            f"```python\n"
            f"import numpy as np\n"
            f"from sklearn.model_selection import train_test_split\n\n"
            f"# 1. 生成示例数据\n"
            f"np.random.seed(42)\n"
            f"X = np.random.randn(100, 3)\n"
            f"y = (X[:, 0] + X[:, 1] > 0).astype(int)\n"
            f"X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)\n\n"
            f"# 2. 实现 {topic} 的核心逻辑\n"
            f"# TODO: 在此处实现 {topic} 的算法\n"
            f"# 提示：参考课程讲解中的公式和伪代码\n\n"
            f"class {var_name.capitalize()}Model:\n"
            f'    """{topic} 的简化实现"""\n\n'
            f"    def __init__(self, learning_rate=0.01, max_iter=1000):\n"
            f"        self.lr = learning_rate\n"
            f"        self.max_iter = max_iter\n"
            f"        self.weights = None\n\n"
            f"    def fit(self, X, y):\n"
            f"        n_samples, n_features = X.shape\n"
            f"        self.weights = np.zeros(n_features)\n"
            f"        for _ in range(self.max_iter):\n"
            f"            # 计算梯度 ∇L(w)\n"
            f"            gradients = self._compute_gradients(X, y)\n"
            f"            # 更新权重 w = w - η * ∇L(w)\n"
            f"            self.weights -= self.lr * gradients\n"
            f"        return self\n\n"
            f"    def predict(self, X):\n"
            f"        return (X @ self.weights > 0).astype(int)\n\n"
            f"    def _compute_gradients(self, X, y):\n"
            f"        predictions = X @ self.weights\n"
            f"        errors = predictions - y\n"
            f"        return X.T @ errors / len(y)\n\n"
            f"# 3. 训练与评估\n"
            f"model = {var_name.capitalize()}Model(learning_rate=0.01, max_iter=1000)\n"
            f"model.fit(X_train, y_train)\n"
            f"train_acc = (model.predict(X_train) == y_train).mean()\n"
            f"test_acc = (model.predict(X_test) == y_test).mean()\n"
            f"print(f'训练准确率: {{train_acc:.2%}}')\n"
            f"print(f'测试准确率: {{test_acc:.2%}}')\n"
            f"```\n\n"
            f"## 使用说明\n"
            f"1. 复制代码到本地 .py 文件\n"
            f"2. 确保已安装 numpy 和 scikit-learn\n"
            f"3. 运行 `python <filename>.py`\n"
            f"4. 观察输出结果，尝试修改超参数（learning_rate、max_iter）\n\n"
            f"## 思考题\n"
            f"1. 尝试增大 learning_rate，观察训练过程有何变化？\n"
            f"2. 如果数据量增加到 10000 条，算法性能如何？\n"
            f"3. 能否用 sklearn 中的对应方法验证你的实现？\n\n"
            f"## 扩展练习\n"
            f"- 添加正则化项防止过拟合\n"
            f"- 实现 mini-batch 版本提升效率\n"
            f"- 用真实数据集（如 Iris、Boston Housing）测试\n"
        )
        if rag_context:
            content += f"\n---\n## 知识库参考\n{rag_context}\n"

        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} Python 代码实践",
                content=content,
                content_format="python",
                target_topic=topic,
                difficulty=Difficulty(difficulty),
                personalization_reason=self._personalization_reason(context),
                source_references=references or [],
                review_status="pending",
            ),
            topic, difficulty, references, context,
        )

    def _finalize(
        self,
        draft: Resource,
        topic: str,
        difficulty: str,
        references: list[SourceReference],
        context: SharedAgentContext,
    ) -> Resource:
        return Resource(
            resource_id=draft.resource_id or self._make_resource_id(),
            resource_type=ResourceType.CODING,
            title=draft.title or f"{topic} Python 代码实践",
            content=draft.content,
            content_format="python",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
