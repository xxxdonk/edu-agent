from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Callable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CASE_IDS = {"visual_beginner", "exam_oriented", "project_practice"}
EXPECTED_CHAPTER_COUNT = 8


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: str
    item: str
    detail: str = ""

    def render(self) -> str:
        suffix = f"：{self.detail}" if self.detail else ""
        return f"[{self.status}] {self.item}{suffix}"


def _default_command_probe(command: str) -> bool:
    return shutil.which(command) is not None


def _default_port_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class PreflightChecker:
    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        *,
        command_probe: Callable[[str], bool] = _default_command_probe,
        port_probe: Callable[[int], bool] = _default_port_probe,
        import_probe: Callable[[], None] | None = None,
        schema_probe: Callable[[], None] | None = None,
        openapi_probe: Callable[[], None] | None = None,
        tracked_files: Sequence[str] | None = None,
        python_version: tuple[int, int] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.command_probe = command_probe
        self.port_probe = port_probe
        self.import_probe = import_probe or self._probe_backend_imports
        self.schema_probe = schema_probe or self._probe_public_schema
        self.openapi_probe = openapi_probe or self._probe_openapi
        self._tracked_files_override = list(tracked_files) if tracked_files is not None else None
        self.python_version = python_version or sys.version_info[:2]

    def run(self) -> list[CheckResult]:
        env_path = self.root / ".env"
        env_values = self._read_env(env_path) if env_path.is_file() else {}
        effective_env = {**env_values, **os.environ}
        tracked = self._tracked_files()
        return [
            self._check_python(),
            self._check_node_npm(),
            self._check_env_file(env_path),
            self._check_llm_enabled(effective_env),
            self._check_provider_model(effective_env),
            self._check_api_key(effective_env),
            self._run_probe("后端依赖可导入", self.import_probe),
            self._check_frontend_files(),
            self._check_knowledge_base(),
            self._check_data_directory(),
            self._check_ports(),
            self._run_probe("公共 Schema 可加载", self.schema_probe),
            self._run_probe("OpenAPI 可生成", self.openapi_probe),
            self._check_demo_cases(),
            self._check_file("Windows 一键启动脚本", "scripts/start_demo.ps1"),
            self._check_file("端到端验证脚本", "scripts/verify_end_to_end.py"),
            self._check_file("三案例验证脚本", "scripts/verify_demo_cases.py"),
            self._check_tracked_files(tracked),
            self._check_empty_documents(),
            self._check_conflict_markers(tracked),
        ]

    @staticmethod
    def _read_env(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def _check_python(self) -> CheckResult:
        major, minor = self.python_version
        status = "PASS" if (major, minor) >= (3, 11) else "FAIL"
        return CheckResult(status, "Python 版本", f"{major}.{minor}")

    def _check_node_npm(self) -> CheckResult:
        node_ok = self.command_probe("node")
        npm_ok = self.command_probe("npm.cmd" if os.name == "nt" else "npm")
        status = "PASS" if node_ok and npm_ok else "FAIL"
        detail = "Node 与 npm 可用" if status == "PASS" else "缺少 Node 或 npm"
        return CheckResult(status, "Node/npm", detail)

    @staticmethod
    def _check_env_file(path: Path) -> CheckResult:
        return CheckResult("PASS" if path.is_file() else "FAIL", "根目录 .env", "存在" if path.is_file() else "缺失")

    @staticmethod
    def _check_llm_enabled(env: Mapping[str, str]) -> CheckResult:
        enabled = env.get("ENABLE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}
        return CheckResult("PASS" if enabled else "FAIL", "ENABLE_LLM", "已开启" if enabled else "未开启")

    @staticmethod
    def _check_provider_model(env: Mapping[str, str]) -> CheckResult:
        configured = bool(env.get("LLM_PROVIDER", "").strip() and env.get("LLM_MODEL", "").strip())
        return CheckResult("PASS" if configured else "FAIL", "LLM provider/model", "已配置" if configured else "缺失")

    @staticmethod
    def _check_api_key(env: Mapping[str, str]) -> CheckResult:
        present = bool(env.get("LLM_API_KEY", "").strip())
        return CheckResult("PASS" if present else "FAIL", "LLM API Key", "已配置（值不显示）" if present else "缺失")

    @staticmethod
    def _run_probe(item: str, probe: Callable[[], None]) -> CheckResult:
        try:
            probe()
        except Exception as error:
            return CheckResult("FAIL", item, type(error).__name__)
        return CheckResult("PASS", item)

    def _check_frontend_files(self) -> CheckResult:
        required = (self.root / "frontend/package.json", self.root / "frontend/package-lock.json")
        ok = all(path.is_file() for path in required)
        return CheckResult("PASS" if ok else "FAIL", "前端 package 与 lock 文件", "完整" if ok else "缺失")

    def _check_knowledge_base(self) -> CheckResult:
        root = self.root / "data/machine_learning"
        chapters = list(root.glob("[0-9][0-9]-*.md")) if root.is_dir() else []
        supporting = (root / "syllabus.md").is_file() and (root / "sources.json").is_file()
        ok = len(chapters) == EXPECTED_CHAPTER_COUNT and supporting
        detail = f"章节 {len(chapters)}/{EXPECTED_CHAPTER_COUNT}"
        return CheckResult("PASS" if ok else "FAIL", "课程知识库", detail)

    def _check_data_directory(self) -> CheckResult:
        data_dir = self.root / "data"
        ok = data_dir.is_dir() and os.access(data_dir, os.W_OK)
        return CheckResult("PASS" if ok else "FAIL", "SQLite 数据目录可写", "可写" if ok else "不可写或缺失")

    def _check_ports(self) -> CheckResult:
        occupied = [port for port in (8000, 5173) if not self.port_probe(port)]
        return CheckResult("PASS" if not occupied else "FAIL", "演示端口", "8000/5173 空闲" if not occupied else "占用：" + ",".join(map(str, occupied)))

    def _check_demo_cases(self) -> CheckResult:
        path = self.root / "scripts/demo_cases.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cases = payload.get("cases") if isinstance(payload, dict) else None
            ids = {str(case.get("id")) for case in cases} if isinstance(cases, list) else set()
        except (OSError, ValueError):
            ids = set()
        ok = ids == EXPECTED_CASE_IDS
        return CheckResult("PASS" if ok else "FAIL", "演示案例 A/B/C", "完整" if ok else "缺失或格式错误")

    def _check_file(self, item: str, relative_path: str) -> CheckResult:
        ok = (self.root / relative_path).is_file()
        return CheckResult("PASS" if ok else "FAIL", item, "存在" if ok else "缺失")

    def _tracked_files(self) -> list[str]:
        if self._tracked_files_override is not None:
            return list(self._tracked_files_override)
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]

    @staticmethod
    def _check_tracked_files(tracked: Sequence[str]) -> CheckResult:
        unsafe: list[str] = []
        for item in tracked:
            lowered = item.casefold()
            parts = lowered.split("/")
            if lowered == ".env" or any(part in {"node_modules", ".venv", "dist", "__pycache__"} for part in parts) or lowered.endswith((".pyc", ".db", ".sqlite", ".sqlite3", ".log")):
                unsafe.append(item)
        return CheckResult("PASS" if not unsafe else "FAIL", "敏感/运行文件未被 Git 跟踪", "通过" if not unsafe else f"发现 {len(unsafe)} 项")

    def _check_empty_documents(self) -> CheckResult:
        candidates = [self.root / "README.md", *(self.root / "docs").glob("*.md")]
        empty = [path for path in candidates if path.is_file() and path.stat().st_size == 0]
        return CheckResult("PASS" if not empty else "FAIL", "文档非空", "通过" if not empty else f"发现 {len(empty)} 个空文件")

    def _check_conflict_markers(self, tracked: Sequence[str]) -> CheckResult:
        markers = ("<<<<<<<", "=======", ">>>>>>>")
        found = 0
        for relative in tracked:
            path = self.root / relative
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            if any(line.startswith(markers) for line in lines):
                found += 1
        return CheckResult("PASS" if not found else "FAIL", "冲突标记", "无" if not found else f"发现 {found} 个文件")

    def _with_backend_path(self) -> None:
        backend = str(self.root / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)

    def _probe_backend_imports(self) -> None:
        for module in ("fastapi", "pydantic", "httpx", "dotenv", "uvicorn"):
            importlib.import_module(module)

    def _probe_public_schema(self) -> None:
        self._with_backend_path()
        schemas = importlib.import_module("app.schemas")
        schemas.LearningPath.model_json_schema()
        schemas.StudentProfile.model_json_schema()

    def _probe_openapi(self) -> None:
        self._with_backend_path()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            app = importlib.import_module("app.main").app
            document = app.openapi()
        if not isinstance(document, dict) or not document.get("paths"):
            raise ValueError("OpenAPI document is empty")


def main() -> int:
    try:
        results = PreflightChecker().run()
    except Exception as error:
        results = [CheckResult("FAIL", "预检执行", type(error).__name__)]

    for result in results:
        print(result.render())
    failures = sum(result.status == "FAIL" for result in results)
    warnings = sum(result.status == "WARN" for result in results)
    print()
    print(f"是否适合启动演示：{'是' if failures == 0 else '否'}")
    print(f"阻断项数量：{failures}")
    print(f"警告数量：{warnings}")
    next_command = ".\\scripts\\start_demo.ps1" if failures == 0 else ".\\.venv\\Scripts\\python.exe scripts\\preflight_demo.py"
    print(f"推荐下一条命令：{next_command}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
