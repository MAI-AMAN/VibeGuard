import subprocess
import sys
from pathlib import Path

import pytest

from vibeguard.schemas.run import Finding
from vibeguard.workflow.services import (
    EvidenceCollector,
    PatchGenerator,
    ReliabilityAnalyzer,
    RepositoryObserver,
    ReproductionEngine,
    SafeCommandRunner,
)


def make_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/sample.git"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "src" / "sample.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def fragile_finding(path: str = "examples/demo_fragile.py") -> Finding:
    return Finding(
        id="fragile-json-7",
        severity="HIGH",
        confidence="HIGH",
        file=path,
        line="7",
        description="fragile JSON",
        evidence=['json.loads(payload)["retry_after"]'],
        recommendation="validate",
        kind="fragile_json_index",
    )


def test_observer_uses_real_git_data(tmp_path: Path) -> None:
    profile = RepositoryObserver().observe(make_repo(tmp_path))
    assert profile.name == "acme/sample"
    assert profile.branch == "main"
    assert profile.language == "Python"
    assert profile.package_manager == "uv"
    assert profile.recent_commits


def test_analyzer_produces_structured_finding(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "risky.py").write_text(
        "import json\n\ndef parse(raw: str):\n    return json.loads(raw)['required']\n"
    )
    findings = ReliabilityAnalyzer.analyze(tmp_path)
    assert findings[0].kind == "fragile_json_index"
    assert findings[0].severity == "HIGH"
    assert findings[0].file == "src/risky.py"


def test_analyzer_detects_swallowed_exception(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "risky.py").write_text("try:\n    work()\nexcept Exception:\n    pass\n")
    assert ReliabilityAnalyzer.analyze(tmp_path)[0].kind == "swallowed_exception"


def test_evidence_uses_source_and_git(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    finding = Finding(
        id="x",
        severity="HIGH",
        confidence="HIGH",
        file="src/sample.py",
        line="1",
        description="x",
        evidence=[],
        recommendation="x",
        kind="x",
    )
    items = EvidenceCollector().collect(
        repo, finding, RepositoryObserver().observe(repo)
    )
    assert {item.source for item in items} == {"source", "git", "repository"}
    assert "VALUE = 1" in items[0].detail


def test_sandbox_runner_captures_result_and_rejects_commands(tmp_path: Path) -> None:
    result = SafeCommandRunner(tmp_path).run([sys.executable, "-c", "print('safe')"])
    assert result.exit_code == 0 and result.stdout.strip() == "safe"
    with pytest.raises(ValueError, match="allowlisted"):
        SafeCommandRunner(tmp_path).run(["sh", "-c", "echo unsafe"])


def test_reproduction_distinguishes_reproduced(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "__init__.py").write_text("")
    (tmp_path / "examples" / "demo_fragile.py").write_text(
        "import json\ndef parse_retry_after(payload):\n"
        "    return json.loads(payload)['retry_after']\n"
    )
    result = ReproductionEngine(SafeCommandRunner(tmp_path)).reproduce(
        tmp_path, fragile_finding()
    )
    assert result.status == "REPRODUCED"
    assert result.execution.exit_code == 42
    assert "missing key" in result.observed


def test_patch_is_generated_and_applied_only_to_copy(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    original = (
        "import json\n\ndef parse_retry_after(payload: str) -> int:\n"
        '    return int(json.loads(payload)["retry_after"])\n'
    )
    target = tmp_path / "examples" / "demo_fragile.py"
    target.write_text(original)
    proposal = PatchGenerator().generate(tmp_path, fragile_finding())
    copied = PatchGenerator().apply_to_copy(tmp_path, "run", proposal)
    assert target.read_text() == original
    assert (
        '.get("retry_after", 0)'
        in (copied / "examples" / "demo_fragile.py").read_text()
    )
