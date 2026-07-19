"""Guardrail clarity tests for the keyword-based safety checker."""

from __future__ import annotations

from app.guardrails.checker import GuardrailChecker
from app.schemas import (
    Difficulty,
    Resource,
    ResourceType,
    SourceReference,
)


def _create_resource(title: str, content: str, personalization_reason: str = "test") -> Resource:
    return Resource(
        resource_id="res_001",
        resource_type=ResourceType.EXPLANATION,
        title=title,
        content=content,
        content_format="markdown",
        target_topic="机器学习",
        difficulty=Difficulty.BEGINNER,
        personalization_reason=personalization_reason,
        source_references=[SourceReference(source_id="s1", title="ref", locator="http://example.com")],
        review_status="approved",
    )


class TestGuardrailCleanContent:
    def test_clean_content_passes(self):
        resource = _create_resource("线性回归入门", "线性回归通过最小二乘法拟合数据点。")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is True
        assert issues == []

    def test_mindmap_with_normal_content_passes(self):
        resource = _create_resource(
            "决策树思维导图",
            "```mermaid\nmindmap\n  决策树\n    分类\n    回归\n```",
        )
        passed, issues = GuardrailChecker.check(resource)
        assert passed is True

    def test_complex_technical_content_passes(self):
        resource = _create_resource(
            "RNN 结构详解",
            "循环神经网络通过隐藏状态传递时序信息。GRU 使用更新门和重置门控制信息流。",
        )
        passed, issues = GuardrailChecker.check(resource)
        assert passed is True


class TestGuardrailHarmfulContent:
    def test_harmful_keyword_in_content(self):
        resource = _create_resource("安全测试", "介绍如何使用攻击手段获取系统权限。")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is False
        assert any("不安全信息" in issue for issue in issues)

    def test_harmful_keyword_in_title(self):
        resource = _create_resource("入侵教程", "正常的机器学习内容。")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is False
        assert any("标题" in issue for issue in issues)

    def test_harmful_keyword_in_personalization_reason(self):
        resource = _create_resource("测试", "正常内容", personalization_reason="破解相关")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is False
        assert any("个性化理由" in issue for issue in issues)

    def test_harmful_english_keyword(self):
        resource = _create_resource("Test", "How to exploit system vulnerabilities.")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is False

    def test_multiple_harmful_keywords_returns_all_issues(self):
        resource = _create_resource("攻击", "这是一个包含攻击和破解的内容。")
        passed, issues = GuardrailChecker.check(resource)
        assert passed is False
        assert len(issues) >= 2
