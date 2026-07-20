from __future__ import annotations

from app.llm import LLMMessage
from app.orchestrator import SharedAgentContext
from app.schemas import Resource, ResourceType, SourceReference
from app.schemas.common import Difficulty
from app.subjects import subject_context_from_profile

from .base import BaseResourceAgent
from .cross_subject import explanation_resource, should_use_cross_subject


class ExplanationAgent(BaseResourceAgent):
    agent_name = "explanation_agent"
    resource_type = ResourceType.EXPLANATION

    async def _generate_with_llm(
        self,
        context: SharedAgentContext,
        step,
        topic: str,
        difficulty: str,
        rag_context: str,
        references: list[SourceReference],
    ) -> Resource:
        profile = context.profile
        subject = subject_context_from_profile(profile)
        system_prompt = (
            f"你是一位{subject.subject_name or '通识'}课程讲师。根据学生画像和可用课程资料生成完整 Markdown 讲解。"
            "依次包含：学习目标、学习价值、前置回顾、核心概念、原理与闭合 LaTeX 公式、"
            "分步流程、贴合目标的完整示例、至少四个常见错误、至少三个自检问题、"
            "至少五组 FAQ、本节总结和下一步建议。"
            f"内容结构必须适合 {subject.subject_family} 学科；每个必要公式后解释变量含义，不需要公式的学科不得强行加入。"
            "不要虚构结论、来源或统计数据；知识库为空时明确使用通用模型知识。"
            "初学者偏直观，考试目标突出公式与易错点，项目目标突出指标与调试。"
        )
        user_content = (
            f"课程主题：{topic}\n"
            f"难度：{difficulty}\n"
            f"学生薄弱点：{profile.weak_topics.value}\n"
            f"认知风格：{profile.cognitive_style.value}\n"
            f"学习目标：{profile.learning_goals.value}\n"
            f"学习历史：{profile.learning_history.value}\n"
        )
        if rag_context:
            user_content += f"\n知识库参考：\n{rag_context}"
        user_content += "\n请生成一份结构清晰的 Markdown 讲解文档。"

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
            return explanation_resource(context, topic, difficulty, references)
        level_labels = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}
        label = level_labels.get(difficulty, "入门")
        goals = "、".join(context.profile.learning_goals.value or ["掌握当前主题"])
        weak = "、".join(context.profile.weak_topics.value or [topic])
        style = context.profile.cognitive_style.value or "综合型"
        history = "、".join(context.profile.learning_history.value or ["尚未记录相关学习经历"])

        content = (
            f"# {topic} — {label}讲解\n\n"
            f"## 1. 本节学习目标\n"
            f"1. 用自己的话说明{topic}解决的问题与适用边界。\n"
            f"2. 解释目标函数、参数更新与验证指标之间的关系。\n"
            f"3. 围绕“{goals}”完成一个可复现的小实验。\n"
            f"4. 能依据训练与验证结果定位至少两类常见问题。\n\n"
            f"## 2. 为什么需要学习这个知识点\n"
            f"你的目标是{goals}，当前需要重点巩固{weak}。{topic}把问题定义、数据、模型和评价连接起来，"
            f"学会它的价值不只是记住算法名称，而是能解释一次实验为什么这样设计、结果是否可信。\n\n"
            f"## 3. 前置知识快速回顾\n"
            f"先确认样本、特征、标签和数据划分的含义，再回顾函数变化率与向量运算。"
            f"你已有的相关经历是：{history}。本节只使用这些概念理解后续流程。\n\n"
            f"## 4. 核心概念\n"
            f"可以把{topic}理解为：在明确任务与评价标准后，用训练数据寻找一组参数，使模型预测误差尽可能小，"
            f"再用未参与参数更新的数据检查泛化能力。训练表现回答“是否学会训练数据”，验证表现回答“能否迁移到新数据”。\n\n"
            f"## 5. 原理与公式\n"
            f"经验风险写为 \\(J(\\theta)=\\frac{{1}}{{n}}\\sum_{{i=1}}^n L(f_\\theta(x_i),y_i)\\)。"
            f"其中 \\(n\\) 是样本数，\\(x_i\\) 与 \\(y_i\\) 是第 i 个输入和目标，\\(\\theta\\) 是模型参数，\\(L\\) 衡量单个样本误差。\n\n"
            f"梯度下降更新为 \\(\\theta_{{t+1}}=\\theta_t-\\eta\\nabla J(\\theta_t)\\)。"
            f"其中 \\(t\\) 是迭代轮次，\\(\\eta\\) 是学习率，\\(\\nabla J\\) 给出目标函数增长最快的方向，因此更新时取反方向。\n\n"
            f"## 6. 分步执行流程\n"
            f"1. 定义任务：确定输入、输出和成功指标。\n"
            f"2. 检查数据：处理缺失、异常和类别分布，并避免信息泄漏。\n"
            f"3. 建立基线：用简单方案获得可比较结果。\n"
            f"4. 训练模型：记录参数、随机种子和损失变化。\n"
            f"5. 验证结果：比较训练集与验证集，识别欠拟合或过拟合。\n"
            f"6. 有依据地调整：一次只改变少量因素，再用相同指标复验。\n\n"
            f"## 7. 贴合学习目标的完整示例\n"
            f"以客户流失分类为例，输入可包含使用时长、服务次数等特征，输出是是否流失。"
            f"先固定训练/验证划分并建立简单基线，再训练模型，记录验证集上的准确率与召回表现。"
            f"若训练很好而验证明显下降，不应直接宣称模型有效，而应检查过拟合、数据泄漏和参数设置。"
            f"这套流程同样适用于课程小实验，重点是每一步都能复现和解释。\n\n"
            f"## 8. 常见错误与排查\n"
            f"1. **先选模型后定义问题**：回到业务目标，重新写清输入、输出和指标。\n"
            f"2. **在全部数据上预处理后再划分**：将拟合预处理参数限制在训练集。\n"
            f"3. **只看训练指标**：同时查看验证指标及两者差距。\n"
            f"4. **同时修改大量参数**：固定基线，每次记录有限改动及其影响。\n"
            f"5. **把一次随机结果当结论**：固定种子并进行重复验证。\n\n"
            f"## 9. 快速自检\n"
            f"1. 为什么验证集不应参与常规参数更新？\n"
            f"2. 学习率过大时，损失曲线可能出现什么现象？\n"
            f"3. 训练表现很好但验证表现差，下一步应先检查什么？\n"
            f"<details><summary>查看自检提示</summary>验证集用于估计泛化；过大学习率可能造成震荡或发散；应先检查数据划分、泄漏与过拟合。</details>\n\n"
            f"## 10. 常见问答 FAQ\n"
            f"**Q1：需要先背下所有公式吗？** 先理解变量与流程，再通过练习巩固公式。\n\n"
            f"**Q2：指标越高就一定越好吗？** 还要确认数据划分、指标是否匹配目标以及结果是否稳定。\n\n"
            f"**Q3：如何判断参数调整有效？** 与固定基线在相同验证条件下比较。\n\n"
            f"**Q4：为什么要保留随机种子？** 它让数据划分与初始化更容易复现。\n\n"
            f"**Q5：遇到不收敛怎么办？** 依次检查数据尺度、梯度、学习率和实现细节。\n\n"
            f"## 11. 本节总结\n"
            f"{topic}的学习主线是“定义任务 → 建立目标 → 训练 → 验证 → 诊断 → 调整”。"
            f"对{style}学习方式，建议把这条主线与思维导图和小实验配合使用。\n\n"
            f"## 12. 下一步建议\n"
            f"先查看思维导图建立结构，再完成代码实践并记录实验结果，最后用分层 Quiz 检查{weak}是否真正掌握。\n"
        )
        return self._finalize(
            Resource(
                resource_id=self._make_resource_id(),
                resource_type=self.resource_type,
                title=f"{topic} — {label}课程讲解",
                content=content,
                content_format="markdown",
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
            resource_type=ResourceType.EXPLANATION,
            title=draft.title or f"{topic} 课程讲解",
            content=draft.content,
            content_format="markdown",
            target_topic=topic,
            difficulty=draft.difficulty or Difficulty(difficulty),
            personalization_reason=draft.personalization_reason or self._personalization_reason(context),
            source_references=references or draft.source_references,
            review_status="pending",
        )
