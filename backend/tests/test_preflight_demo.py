from __future__ import annotations

import json
from pathlib import Path

from scripts.preflight_demo import PreflightChecker


def _write_minimal_repo(root: Path, *, key: str = "test-secret-value") -> None:
    (root / "frontend").mkdir(parents=True)
    (root / "data/machine_learning").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / ".env").write_text(
        "ENABLE_LLM=true\nLLM_PROVIDER=openai_compatible\n"
        f"LLM_MODEL=test-model\nLLM_API_KEY={key}\n",
        encoding="utf-8",
    )
    (root / "frontend/package.json").write_text("{}", encoding="utf-8")
    (root / "frontend/package-lock.json").write_text("{}", encoding="utf-8")
    for index in range(1, 9):
        (root / f"data/machine_learning/{index:02d}-chapter.md").write_text("# chapter", encoding="utf-8")
    (root / "data/machine_learning/syllabus.md").write_text("# syllabus", encoding="utf-8")
    (root / "data/machine_learning/sources.json").write_text("{}", encoding="utf-8")
    cases = {"cases": [{"id": item} for item in ("visual_beginner", "exam_oriented", "project_practice")]}
    (root / "scripts/demo_cases.json").write_text(json.dumps(cases), encoding="utf-8")
    for name in ("start_demo.ps1", "verify_end_to_end.py", "verify_demo_cases.py"):
        (root / "scripts" / name).write_text("# test", encoding="utf-8")
    (root / "README.md").write_text("# test", encoding="utf-8")


def _checker(root: Path, **overrides) -> PreflightChecker:
    options = {
        "command_probe": lambda _command: True,
        "port_probe": lambda _port: True,
        "import_probe": lambda: None,
        "schema_probe": lambda: None,
        "openapi_probe": lambda: None,
        "tracked_files": [],
        "python_version": (3, 13),
    }
    options.update(overrides)
    return PreflightChecker(root, **options)


def _result(checker: PreflightChecker, item: str):
    return next(result for result in checker.run() if result.item == item)


def test_preflight_reports_missing_env(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / ".env").unlink()

    assert _result(_checker(tmp_path), "根目录 .env").status == "FAIL"


def test_preflight_reports_occupied_port(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    checker = _checker(tmp_path, port_probe=lambda port: port != 8000)

    result = _result(checker, "演示端口")
    assert result.status == "FAIL"
    assert "8000" in result.detail


def test_preflight_reports_missing_knowledge_base(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    for path in (tmp_path / "data/machine_learning").glob("*"):
        path.unlink()

    assert _result(_checker(tmp_path), "课程知识库").status == "FAIL"


def test_preflight_never_renders_api_key(tmp_path: Path) -> None:
    secret = "test-secret-must-not-leak"
    _write_minimal_repo(tmp_path, key=secret)

    rendered = "\n".join(result.render() for result in _checker(tmp_path).run())
    assert "LLM API Key" in rendered
    assert secret not in rendered


def test_preflight_all_checks_pass(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    results = _checker(tmp_path).run()

    assert len(results) == 20
    assert all(result.status == "PASS" for result in results)


def test_preflight_handles_windows_style_root_with_spaces(tmp_path: Path) -> None:
    root = tmp_path / "Edu Agent Windows Path"
    _write_minimal_repo(root)

    results = _checker(Path(str(root))).run()

    assert all(result.status == "PASS" for result in results)
