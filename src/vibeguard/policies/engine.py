"""Fail-closed policy decisions for repository and external actions."""

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch


class Action(StrEnum):
    OBSERVE = "observe"
    ANALYZE = "analyze"
    REPRODUCE = "reproduce"
    APPLY_PATCH = "apply_patch"
    CREATE_BRANCH = "create_branch"
    COMMIT_FILES = "commit_files"
    OPEN_DRAFT_PR = "open_draft_pr"
    MERGE_PR = "merge_pr"
    FORCE_PUSH = "force_push"
    DELETE_RESOURCE = "delete_resource"
    DEPLOY_PRODUCTION = "deploy_production"
    MANIPULATE_CREDENTIALS = "manipulate_credentials"


class PolicyLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class PolicyConfig:
    allowed_repositories: frozenset[str] = frozenset()
    max_changed_files: int = 5
    max_diff_lines: int = 250


@dataclass(frozen=True)
class PolicyRequest:
    repository: str
    action: Action
    changed_files: tuple[str, ...] = ()
    diff_lines: int = 0
    approval_valid: bool = False
    base_sha: str | None = None
    approved_base_sha: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    level: PolicyLevel


FORBIDDEN_PATHS = (".env", ".env.*", "*.pem", "*.key", "*credentials*", ".git/*")
READ_ACTIONS = {Action.OBSERVE, Action.ANALYZE, Action.REPRODUCE}
APPROVAL_ACTIONS = {
    Action.APPLY_PATCH,
    Action.CREATE_BRANCH,
    Action.COMMIT_FILES,
    Action.OPEN_DRAFT_PR,
}
FORBIDDEN_ACTIONS = {
    Action.MERGE_PR,
    Action.FORCE_PUSH,
    Action.DELETE_RESOURCE,
    Action.DEPLOY_PRODUCTION,
    Action.MANIPULATE_CREDENTIALS,
}


class PolicyEngine:
    def __init__(self, config: PolicyConfig) -> None:
        self.config = config

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        if request.repository not in self.config.allowed_repositories:
            return PolicyDecision(
                False, "repository is not allowlisted", PolicyLevel.FORBIDDEN
            )
        if request.action in FORBIDDEN_ACTIONS:
            return PolicyDecision(
                False, f"{request.action.value} is forbidden", PolicyLevel.FORBIDDEN
            )
        if any(self._is_forbidden_path(path) for path in request.changed_files):
            return PolicyDecision(
                False, "change includes a forbidden path", PolicyLevel.FORBIDDEN
            )
        if len(request.changed_files) > self.config.max_changed_files:
            return PolicyDecision(
                False, "too many changed files", PolicyLevel.FORBIDDEN
            )
        if request.diff_lines > self.config.max_diff_lines:
            return PolicyDecision(
                False, "diff exceeds configured limit", PolicyLevel.FORBIDDEN
            )
        if (
            request.approved_base_sha is not None
            and request.base_sha != request.approved_base_sha
        ):
            return PolicyDecision(
                False, "base SHA does not match approved SHA", PolicyLevel.FORBIDDEN
            )
        if request.action in READ_ACTIONS:
            return PolicyDecision(True, "read-only action", PolicyLevel.READ_ONLY)
        if request.action in APPROVAL_ACTIONS and not request.approval_valid:
            return PolicyDecision(
                False, "valid human approval is required", PolicyLevel.REQUIRES_APPROVAL
            )
        if request.action in APPROVAL_ACTIONS:
            return PolicyDecision(
                True, "approved action is within policy", PolicyLevel.REQUIRES_APPROVAL
            )
        return PolicyDecision(False, "unknown action denied", PolicyLevel.FORBIDDEN)

    @staticmethod
    def _is_forbidden_path(path: str) -> bool:
        normalized = path.removeprefix("./")
        if normalized.startswith(".github/workflows/"):
            return True
        return any(fnmatch(normalized, pattern) for pattern in FORBIDDEN_PATHS)
