import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from vibeguard.schemas.run import CommandResult, VerificationResult
from vibeguard.workflow.orchestrator import ApprovalRequired, Orchestrator
from vibeguard.workflow.services import VerificationEngine
from vibeguard.workflow.states import State


def repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/demo.git"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "__init__.py").write_text("")
    (tmp_path / "examples" / "demo_fragile.py").write_text(
        "import json\n\ndef parse_retry_after(payload: str) -> int:\n"
        '    return int(json.loads(payload)["retry_after"])\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("OK = True\n")
    (tmp_path / "tests").mkdir()
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def check(code: int = 0) -> CommandResult:
    return CommandResult(command=["python"], exit_code=code)


def test_audit_stops_at_first_gate_without_modification(tmp_path: Path) -> None:
    root = repo(tmp_path)
    original = (root / "examples" / "demo_fragile.py").read_text()
    run = Orchestrator(root).audit()
    assert run.state is State.WAITING_FOR_REMEDIATION_APPROVAL
    assert run.reproduction and run.reproduction.status == "REPRODUCED"
    assert (root / "examples" / "demo_fragile.py").read_text() == original


def test_each_gate_requires_explicit_approval(tmp_path: Path) -> None:
    flow = Orchestrator(repo(tmp_path))
    run = flow.audit()
    with pytest.raises(ApprovalRequired):
        flow.generate_patch(run.run_id, False)
    run = flow.generate_patch(run.run_id, True)
    assert run.state is State.WAITING_FOR_PATCH_APPROVAL
    with pytest.raises(ApprovalRequired):
        flow.verify(run.run_id, False)


def test_failed_verification_blocks_shipment(tmp_path: Path) -> None:
    flow = Orchestrator(repo(tmp_path))
    run = flow.generate_patch(flow.audit().run_id, True)
    with patch.object(
        VerificationEngine,
        "verify",
        return_value=VerificationResult(passed=False, checks=[check(1)]),
    ):
        run = flow.verify(run.run_id, True)
    assert run.state is State.FAILED
    with pytest.raises(ValueError):
        flow.ship(run.run_id, True)


def test_successful_verification_reaches_third_gate_and_ship_still_requires_approval(
    tmp_path: Path,
) -> None:
    flow = Orchestrator(repo(tmp_path))
    run = flow.generate_patch(flow.audit().run_id, True)
    with patch.object(
        VerificationEngine,
        "verify",
        return_value=VerificationResult(passed=True, checks=[check()]),
    ):
        run = flow.verify(run.run_id, True)
    assert run.state is State.WAITING_FOR_SHIPMENT_APPROVAL
    with pytest.raises(ApprovalRequired):
        flow.ship(run.run_id, False)
    run = flow.ship(run.run_id, True)
    assert run.state is State.SHIPPING
    assert run.shipment and run.shipment["status"] == "READY_FOR_TRUEFORGE_MCP"


def test_real_shipment_result_completes_run(tmp_path: Path) -> None:
    flow = Orchestrator(repo(tmp_path))
    run = flow.generate_patch(flow.audit().run_id, True)
    with patch.object(
        VerificationEngine,
        "verify",
        return_value=VerificationResult(passed=True, checks=[check()]),
    ):
        run = flow.verify(run.run_id, True)
    run = flow.ship(run.run_id, True)
    run = flow.record_shipment(
        run.run_id, "vibeguard/fix", "https://github.com/acme/demo/pull/1"
    )
    assert run.state is State.COMPLETED
    assert run.shipment and run.shipment["pull_request_url"].endswith("/1")
