"""Human-gated VibeGuard orchestration."""

from pathlib import Path

from vibeguard.audit.events import RunStore
from vibeguard.schemas.proposal import PatchProposal
from vibeguard.schemas.run import Approval, AuditRun
from vibeguard.workflow.services import (
    EvidenceCollector,
    PatchGenerator,
    ReliabilityAnalyzer,
    RepositoryObserver,
    ReproductionEngine,
    SafeCommandRunner,
    VerificationEngine,
)
from vibeguard.workflow.states import State


class ApprovalRequired(RuntimeError):
    pass


class Orchestrator:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self.store = RunStore(self.repository)

    def audit(self) -> AuditRun:
        run = self.store.create(self.repository.name)
        try:
            self.store.move(run, State.OBSERVING, "Discovering repository")
            run.profile = RepositoryObserver().observe(self.repository)
            run.repository, run.branch = run.profile.name, run.profile.branch
            self.store.save(run)
            self.store.move(
                run, State.ANALYZING, "Analyzing source for reliability risks"
            )
            findings = ReliabilityAnalyzer.analyze(self.repository)
            if not findings:
                self.store.move(
                    run, State.COMPLETED, "No actionable reliability finding detected"
                )
                return run
            run.finding = findings[0]
            self.store.save(run)
            self.store.move(
                run, State.COLLECTING_EVIDENCE, "Collecting source and Git evidence"
            )
            run.evidence = EvidenceCollector().collect(
                self.repository, run.finding, run.profile
            )
            self.store.save(run)
            self.store.move(run, State.REPRODUCING, "Executing isolated reproduction")
            run.reproduction = ReproductionEngine(
                SafeCommandRunner(self.repository)
            ).reproduce(self.repository, run.finding)
            self.store.save(run)
            self.store.move(
                run,
                State.WAITING_FOR_REMEDIATION_APPROVAL,
                "Human remediation approval required before patch generation",
            )
        except (OSError, ValueError, RuntimeError) as error:
            run.error = str(error)
            if run.state not in {State.COMPLETED, State.FAILED}:
                self.store.move(run, State.FAILED, "Audit failed", error=str(error))
        return run

    def generate_patch(self, run_id: str, approved: bool) -> AuditRun:
        run = self.store.load(run_id)
        self._require_state(run, State.WAITING_FOR_REMEDIATION_APPROVAL)
        if not approved:
            raise ApprovalRequired("Explicit remediation approval is required")
        run.approvals.append(Approval(gate="remediation", approved=True))
        self.store.move(
            run,
            State.GENERATING_PATCH,
            "Remediation approved; generating minimal patch",
        )
        assert run.finding is not None
        proposal = PatchGenerator().generate(self.repository, run.finding)
        run.patch, run.patch_files = proposal.patch, proposal.files
        self.store.save(run)
        self.store.move(
            run, State.WAITING_FOR_PATCH_APPROVAL, "Patch review approval required"
        )
        return run

    def verify(self, run_id: str, approved: bool) -> AuditRun:
        run = self.store.load(run_id)
        self._require_state(run, State.WAITING_FOR_PATCH_APPROVAL)
        if not approved:
            raise ApprovalRequired("Explicit patch approval is required")
        run.approvals.append(Approval(gate="patch", approved=True))
        self.store.move(
            run, State.VERIFYING, "Patch approved; verifying in isolated worktree"
        )
        assert run.finding is not None and run.patch is not None
        proposal = PatchProposal(
            patch=run.patch, files=run.patch_files, reason=run.finding.recommendation
        )
        worktree = PatchGenerator().apply_to_copy(self.repository, run.run_id, proposal)
        run.verification = VerificationEngine().verify(worktree, run.finding)
        self.store.save(run)
        if not run.verification.passed:
            run.error = "Verification failed; shipment blocked"
            self.store.move(run, State.FAILED, run.error)
        else:
            self.store.move(
                run, State.WAITING_FOR_SHIPMENT_APPROVAL, "Shipment approval required"
            )
        return run

    def ship(self, run_id: str, approved: bool) -> AuditRun:
        run = self.store.load(run_id)
        self._require_state(run, State.WAITING_FOR_SHIPMENT_APPROVAL)
        if not approved:
            raise ApprovalRequired("Explicit shipment approval is required")
        if run.verification is None or not run.verification.passed:
            raise RuntimeError("Unverified patches cannot be shipped")
        run.approvals.append(Approval(gate="shipment", approved=True))
        self.store.move(run, State.SHIPPING, "Shipment approved")
        run.shipment = {
            "status": "READY_FOR_TRUEFORGE_MCP",
            "message": (
                "Verified patch ready; invoke the connected GitHub MCP to create a branch and PR."
            ),
        }
        self.store.save(run)
        # CLI code cannot impersonate the host's MCP authority. Completion is performed by
        # the TrueForge host after it records the real branch/PR result with record_shipment.
        return run

    def record_shipment(
        self, run_id: str, branch: str, pull_request_url: str
    ) -> AuditRun:
        run = self.store.load(run_id)
        self._require_state(run, State.SHIPPING)
        run.shipment = {
            "status": "SHIPPED",
            "branch": branch,
            "pull_request_url": pull_request_url,
        }
        self.store.save(run)
        self.store.move(run, State.COMPLETED, "GitHub pull request created")
        return run

    @staticmethod
    def _require_state(run: AuditRun, expected: State) -> None:
        if run.state is not expected:
            raise ValueError(
                f"Run {run.run_id} is {run.state.value}; expected {expected.value}"
            )
