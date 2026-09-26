"""Persistent run models."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from vibeguard.workflow.states import State


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Finding(BaseModel):
    id: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    file: str
    line: str | None = None
    description: str
    evidence: list[str] = Field(default_factory=list)
    recommendation: str
    kind: str


class EvidenceItem(BaseModel):
    source: str
    detail: str
    reference: str | None = None


class CommandResult(BaseModel):
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int
    duration_ms: int = 0


class ReproductionResult(BaseModel):
    status: Literal["REPRODUCED", "NOT_REPRODUCED", "EXECUTION_ERROR"]
    expected: str
    observed: str
    execution: CommandResult


class VerificationResult(BaseModel):
    passed: bool
    checks: list[CommandResult] = Field(default_factory=list)


class Approval(BaseModel):
    gate: Literal["remediation", "patch", "shipment"]
    approved: bool
    approved_at: str = Field(default_factory=now_iso)
    actor: str = "human"


class RunEvent(BaseModel):
    event: str
    run_id: str
    state: State
    message: str
    timestamp: str = Field(default_factory=now_iso)
    data: dict[str, Any] = Field(default_factory=dict)


class RepositoryProfile(BaseModel):
    path: str
    name: str
    branch: str
    head_sha: str
    language: str
    package_manager: str
    test_framework: str
    framework: str | None = None
    important_directories: list[str] = Field(default_factory=list)
    recent_commits: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


class AuditRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    repository: str
    branch: str = ""
    state: State = State.IDLE
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    profile: RepositoryProfile | None = None
    finding: Finding | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reproduction: ReproductionResult | None = None
    approvals: list[Approval] = Field(default_factory=list)
    patch: str | None = None
    patch_files: list[str] = Field(default_factory=list)
    verification: VerificationResult | None = None
    shipment: dict[str, Any] | None = None
    error: str | None = None

    def has_approval(self, gate: str) -> bool:
        return any(a.gate == gate and a.approved for a in self.approvals)
