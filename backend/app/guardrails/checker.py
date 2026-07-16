from __future__ import annotations

from app.schemas import Resource


class GuardrailChecker:
    @staticmethod
    def check(resource: Resource) -> tuple[bool, list[str]]:
        issues: list[str] = []

        if GuardrailChecker._contains_harmful(resource.content):
            issues.append("内容包含不安全信息")
        if GuardrailChecker._contains_harmful(resource.title):
            issues.append("标题包含不安全信息")
        if GuardrailChecker._contains_harmful(resource.personalization_reason):
            issues.append("个性化理由包含不安全信息")

        return len(issues) == 0, issues

    @staticmethod
    def _contains_harmful(text: str) -> bool:
        harmful_keywords = [
            "攻击", "入侵", "破解", "盗版", "恶意代码",
            "attack", "hack", "crack", "exploit", "malware",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in harmful_keywords)
