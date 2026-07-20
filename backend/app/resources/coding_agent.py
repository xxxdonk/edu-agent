from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import subject_context_from_profile

from .base import BaseResourceAgent
from .cross_subject import practice_resource, should_use_cross_subject


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
        subject = subject_context_from_profile(context.profile)
        is_computational = subject.subject_family in {
            "computer_science", "mathematics", "natural_science", "engineering"
        }
        system_prompt = (
            f"你是一位{subject.subject_name or '通识'}课程实践导师。"
            + ("生成可独立运行的计算或实验实践。" if is_computational else "生成不含无意义代码的应用实践任务。")
            + "必须包含实践目标、准备条件、3 至 6 个步骤、预期产出、自评或调试提示和进阶挑战。"
            + "优先围绕学生目标；需要代码时只使用 Python 标准库，不访问外网、不安装依赖，"
            + "不使用绝对路径、密钥、危险系统命令或删除操作，不虚构实验结果。"
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

        return await self._generate_with_one_format_repair(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_content)],
            response_model=Resource,
            finalize=lambda draft: self._finalize(
                draft, topic, difficulty, references, context
            ),
        )

    def _generate_heuristic(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        if should_use_cross_subject(context):
            return practice_resource(context, topic, difficulty, references)
        level_labels = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}
        label = level_labels.get(difficulty, "入门")

        goals = "、".join(context.profile.learning_goals.value or ["完成分类实验"])
        weak = "、".join(context.profile.weak_topics.value or [topic])
        code = '''import math
import random


def sigmoid(value):
    """将线性得分转换为 0 到 1 的概率。"""
    value = max(min(value, 30.0), -30.0)
    return 1.0 / (1.0 + math.exp(-value))


def make_churn_data(size=120, seed=42):
    """生成不含个人信息的客户流失合成数据。"""
    rng = random.Random(seed)
    rows = []
    for _ in range(size):
        months = rng.randint(1, 72) / 72
        support_calls = rng.randint(0, 8) / 8
        monthly_fee = rng.uniform(20, 120) / 120
        score = -1.8 * months + 2.2 * support_calls + 1.1 * monthly_fee - 0.4
        label = int(rng.random() < sigmoid(score))
        rows.append(([1.0, months, support_calls, monthly_fee], label))
    rng.shuffle(rows)
    return rows


def train_logistic_regression(rows, learning_rate=0.35, epochs=300):
    weights = [0.0] * len(rows[0][0])
    for _ in range(epochs):
        gradient = [0.0] * len(weights)
        for features, label in rows:
            probability = sigmoid(sum(w * x for w, x in zip(weights, features)))
            for index, feature in enumerate(features):
                gradient[index] += (probability - label) * feature
        for index in range(len(weights)):
            weights[index] -= learning_rate * gradient[index] / len(rows)
    return weights


def predict(weights, features, threshold=0.5):
    probability = sigmoid(sum(w * x for w, x in zip(weights, features)))
    return int(probability >= threshold)


def confusion_matrix(weights, rows, threshold=0.5):
    matrix = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    for features, label in rows:
        prediction = predict(weights, features, threshold)
        key = ("t" if prediction == label else "f") + ("p" if prediction else "n")
        matrix[key] += 1
    return matrix


def metrics(matrix):
    total = sum(matrix.values())
    accuracy = (matrix["tp"] + matrix["tn"]) / total
    precision = matrix["tp"] / max(matrix["tp"] + matrix["fp"], 1)
    recall = matrix["tp"] / max(matrix["tp"] + matrix["fn"], 1)
    return accuracy, precision, recall


data = make_churn_data()
split = int(len(data) * 0.8)
train_rows, validation_rows = data[:split], data[split:]
weights = train_logistic_regression(train_rows)
matrix = confusion_matrix(weights, validation_rows)
accuracy, precision, recall = metrics(matrix)

print("验证样本数:", len(validation_rows))
print("混淆矩阵:", matrix)
print(f"准确率={accuracy:.3f}, 精确率={precision:.3f}, 召回率={recall:.3f}")
'''
        content = (
            f"# {topic} — 客户流失分类小实验（{label}）\n\n"
            f"## 1. 实验目标\n围绕“{goals}”，用可复现的小实验巩固{weak}，理解训练、阈值和分类指标的关系。\n\n"
            "## 2. 环境说明\n- Python 3.10+\n- 仅使用标准库 `math` 与 `random`\n- 不访问外网，不自动安装依赖\n\n"
            "## 3. 输入数据说明\n使用固定随机种子生成 120 条合成客户记录，仅用于学习。特征包括使用时长、客服次数和月费用，标签表示是否流失。\n\n"
            "## 4. 分步骤任务\n1. 阅读数据生成逻辑，确认特征缩放范围。\n2. 理解逻辑回归概率与梯度更新。\n3. 固定训练/验证划分并训练模型。\n4. 从混淆矩阵计算准确率、精确率和召回率。\n5. 调整阈值并解释项目取舍。\n\n"
            f"## 5. 完整 Python 代码\n```python\n{code}```\n\n"
            "## 6. 预期输出\n程序会输出 24 条验证样本、一个包含 tp/tn/fp/fn 的混淆矩阵，以及 0 到 1 之间的三项指标。具体数值由代码和环境决定，不代表真实业务模型效果。\n\n"
            "## 7. TODO 练习\n1. 将分类阈值改为 0.4，比较召回率变化。\n2. 在梯度中加入 L2 正则项，并记录验证结果。\n3. 增加一个合成特征，说明它是否应进入模型。\n\n"
            "## 8. 调试提示\n1. 若出现溢出，确认 sigmoid 输入已限制范围。\n2. 若指标异常，先打印混淆矩阵并核对 key 的含义。\n3. 若每次结果不同，检查随机种子和数据划分。\n4. 若损失不稳定，减小学习率并增加迭代轮数。\n\n"
            "## 9. 进阶挑战\n1. 实现不同阈值下的指标表，选择符合项目目标的阈值。\n2. 实现三折交叉验证，比较单次划分与多次验证的稳定性。\n\n"
            "## 10. 反思问题\n1. 客户流失项目中漏判与误判的代价是否相同？\n2. 为什么不能用训练指标直接决定上线方案？\n3. 合成数据实验能证明什么，又不能证明什么？\n"
        )

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
            content_format=draft.content_format,
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
