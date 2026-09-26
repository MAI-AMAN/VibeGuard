"""Concrete repository, analysis, sandbox, patch, and verification services."""

import ast
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import ClassVar, Literal

from vibeguard.schemas.proposal import PatchProposal
from vibeguard.schemas.run import (
    CommandResult,
    EvidenceItem,
    Finding,
    RepositoryProfile,
    ReproductionResult,
    VerificationResult,
)


class SafeCommandRunner:
    ALLOWED: ClassVar[set[str]] = {
        "python",
        "python3",
        Path(sys.executable).name,
        "pytest",
        "ruff",
        "mypy",
    }

    def __init__(self, root: Path, timeout: int = 60) -> None:
        self.root = root.resolve()
        self.timeout = timeout

    def run(self, command: list[str], cwd: Path | None = None) -> CommandResult:
        if not command or Path(command[0]).name not in self.ALLOWED:
            raise ValueError(f"Command is not allowlisted: {shlex.join(command)}")
        working = (cwd or self.root).resolve()
        if working != self.root and self.root not in working.parents:
            raise ValueError("Working directory escapes repository sandbox")
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=working,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": os.pathsep.join(
                        (str(self.root), str(self.root / "src"))
                    ),
                },
                check=False,
            )
            return CommandResult(
                command=command,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except subprocess.TimeoutExpired as error:
            return CommandResult(
                command=command,
                stdout=(
                    error.stdout.decode()
                    if isinstance(error.stdout, bytes)
                    else error.stdout
                )
                or "",
                stderr=(
                    (
                        error.stderr.decode()
                        if isinstance(error.stderr, bytes)
                        else error.stderr
                    )
                    or ""
                )
                + "\nCommand timed out",
                exit_code=124,
                duration_ms=int((time.monotonic() - started) * 1000),
            )


class RepositoryObserver:
    def observe(self, root: Path) -> RepositoryProfile:
        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
            return result.stdout.strip()

        files = [
            p for p in root.iterdir() if p.name not in {".git", ".vibeguard", ".venv"}
        ]
        extensions: dict[str, int] = {}
        for path in root.rglob("*"):
            if path.is_file() and not any(
                part.startswith(".") for part in path.relative_to(root).parts
            ):
                extensions[path.suffix] = extensions.get(path.suffix, 0) + 1
        known = {
            suffix: count
            for suffix, count in extensions.items()
            if suffix in {".py", ".ts", ".js"}
        }
        dominant = max(known, key=lambda suffix: known[suffix]) if known else ""
        language = {".py": "Python", ".ts": "TypeScript", ".js": "JavaScript"}.get(
            dominant, "Unknown"
        )
        manager = "uv" if (root / "uv.lock").exists() else "pip"
        test_framework = "pytest" if (root / "tests").exists() else "unknown"
        commits = git("log", "-5", "--pretty=%h %s").splitlines()
        changed = (
            git("diff", "--name-only", "HEAD~1", "HEAD").splitlines()
            if len(commits) > 1
            else []
        )
        remote = git("config", "--get", "remote.origin.url")
        name = remote.removesuffix(".git").rsplit("/", 2)[-2:]
        repo_name = "/".join(name) if len(name) == 2 else root.name
        return RepositoryProfile(
            path=str(root),
            name=repo_name,
            branch=git("branch", "--show-current") or "detached",
            head_sha=git("rev-parse", "HEAD"),
            language=language,
            package_manager=manager,
            test_framework=test_framework,
            important_directories=sorted(p.name for p in files if p.is_dir()),
            recent_commits=commits,
            changed_files=changed,
        )


class ReliabilityAnalyzer(ast.NodeVisitor):
    def __init__(self, relative_path: str, source: str) -> None:
        self.path = relative_path
        self.source = source
        self.findings: list[Finding] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        swallowed = not node.body or all(
            isinstance(item, (ast.Pass, ast.Continue)) for item in node.body
        )
        broad = node.type is None or (
            isinstance(node.type, ast.Name)
            and node.type.id in {"Exception", "BaseException"}
        )
        if broad and swallowed:
            self.findings.append(
                Finding(
                    id=f"swallowed-exception-{node.lineno}",
                    severity="HIGH",
                    confidence="HIGH",
                    file=self.path,
                    line=str(node.lineno),
                    description="A broad exception is swallowed, hiding operational failures.",
                    evidence=[
                        ast.get_source_segment(self.source, node)
                        or "broad exception handler"
                    ],
                    recommendation=(
                        "Catch the expected exception and return or log an explicit failure."
                    ),
                    kind="swallowed_exception",
                )
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        value = node.value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
            owner = value.func.value
            if (
                isinstance(owner, ast.Name)
                and owner.id == "json"
                and value.func.attr == "loads"
            ):
                self.findings.append(
                    Finding(
                        id=f"fragile-json-{node.lineno}",
                        severity="HIGH",
                        confidence="HIGH",
                        file=self.path,
                        line=str(node.lineno),
                        description=(
                            "Unvalidated JSON is indexed directly and raises KeyError "
                            "on a missing field."
                        ),
                        evidence=[
                            ast.get_source_segment(self.source, node)
                            or "json.loads(...)[key]"
                        ],
                        recommendation=(
                            "Validate the decoded object and use an explicit default or error."
                        ),
                        kind="fragile_json_index",
                    )
                )
        self.generic_visit(node)

    @classmethod
    def analyze(cls, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for base in (root / "src", root / "examples"):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                source = path.read_text()
                try:
                    visitor = cls(str(path.relative_to(root)), source)
                    visitor.visit(ast.parse(source))
                    findings.extend(visitor.findings)
                except (SyntaxError, UnicodeDecodeError):
                    continue
        rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        return sorted(
            findings, key=lambda finding: rank[finding.severity], reverse=True
        )


class EvidenceCollector:
    def collect(
        self, root: Path, finding: Finding, profile: RepositoryProfile
    ) -> list[EvidenceItem]:
        path = root / finding.file
        line = int(finding.line or "1")
        source_lines = path.read_text().splitlines()
        excerpt = source_lines[line - 1].strip() if line <= len(source_lines) else ""
        history = subprocess.run(
            ["git", "log", "-3", "--oneline", "--", finding.file],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        ).stdout.strip()
        evidence = [
            EvidenceItem(source="source", detail=f"{finding.file}:{line}: {excerpt}"),
            EvidenceItem(
                source="git", detail=history or "No file-specific commit history found."
            ),
            EvidenceItem(
                source="repository",
                detail=f"HEAD {profile.head_sha} on {profile.branch}",
            ),
        ]
        return evidence


class ReproductionEngine:
    def __init__(self, runner: SafeCommandRunner) -> None:
        self.runner = runner

    def reproduce(self, root: Path, finding: Finding) -> ReproductionResult:
        script = root / ".vibeguard" / "reproduce.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        if finding.kind == "fragile_json_index":
            module = finding.file.removesuffix(".py").replace("/", ".")
            if module.startswith("examples."):
                function = "parse_retry_after"
                code = (
                    f"from {module} import {function}\n"
                    "try:\n"
                    f"    {function}('{{}}')\n"
                    "except KeyError as exc:\n"
                    "    print(f'REPRODUCED: missing key raised {exc!r}')\n"
                    "    raise SystemExit(42)\n"
                    "raise SystemExit(0)\n"
                )
            else:
                code = "raise SystemExit(3)\n"
            script.write_text(code)
            result = self.runner.run([sys.executable, str(script)], root)
            status: Literal["REPRODUCED", "NOT_REPRODUCED", "EXECUTION_ERROR"]
            status = (
                "REPRODUCED"
                if result.exit_code == 42
                else (
                    "EXECUTION_ERROR"
                    if result.exit_code not in {0, 42}
                    else "NOT_REPRODUCED"
                )
            )
            return ReproductionResult(
                status=status,
                expected="Missing JSON fields are handled without an uncaught KeyError.",
                observed=(result.stdout or result.stderr).strip(),
                execution=result,
            )
        script.write_text("print('Static finding has no safe dynamic reproducer')\n")
        result = self.runner.run([sys.executable, str(script)], root)
        return ReproductionResult(
            status="NOT_REPRODUCED",
            expected="A dynamic failure",
            observed=result.stdout.strip(),
            execution=result,
        )


class PatchGenerator:
    def generate(self, root: Path, finding: Finding) -> PatchProposal:
        if finding.kind != "fragile_json_index":
            raise ValueError(f"No safe automatic patch is available for {finding.kind}")
        path = root / finding.file
        old = path.read_text()
        needle = 'return int(json.loads(payload)["retry_after"])'
        replacement = (
            "data = json.loads(payload)\n"
            '    retry_after = data.get("retry_after", 0)\n'
            "    if not isinstance(retry_after, (int, str)):\n"
            '        raise ValueError("retry_after must be an integer")\n'
            "    return int(retry_after)"
        )
        if needle not in old:
            raise ValueError("Expected vulnerable expression no longer exists")
        new = old.replace(needle, replacement, 1)
        import difflib

        patch = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{finding.file}",
                tofile=f"b/{finding.file}",
            )
        )
        return PatchProposal(
            patch=patch, files=[finding.file], reason=finding.recommendation
        )

    def apply_to_copy(self, root: Path, run_id: str, proposal: PatchProposal) -> Path:
        worktree = root / ".vibeguard" / "runs" / run_id / "worktree"
        if worktree.exists():
            shutil.rmtree(worktree)
        shutil.copytree(
            root, worktree, ignore=shutil.ignore_patterns(".git", ".venv", ".vibeguard")
        )
        result = subprocess.run(
            ["git", "apply", "--unsafe-paths", "-"],
            cwd=worktree,
            input=proposal.patch,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Patch application failed: {result.stderr}")
        return worktree


class VerificationEngine:
    def verify(self, worktree: Path, finding: Finding) -> VerificationResult:
        runner = SafeCommandRunner(worktree, timeout=120)
        checks = [runner.run([sys.executable, "-m", "pytest", "-q"], worktree)]
        if finding.kind == "fragile_json_index":
            checks.append(
                runner.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "from examples.demo_fragile import parse_retry_after; "
                            "assert parse_retry_after('{}') == 0; print('regression fixed')"
                        ),
                    ],
                    worktree,
                )
            )
        checks.append(
            runner.run([sys.executable, "-m", "ruff", "check", "."], worktree)
        )
        checks.append(runner.run([sys.executable, "-m", "mypy", "src"], worktree))
        return VerificationResult(
            passed=all(check.exit_code == 0 for check in checks), checks=checks
        )
