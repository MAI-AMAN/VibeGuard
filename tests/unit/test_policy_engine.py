from vibeguard.policies.engine import (
    Action,
    PolicyConfig,
    PolicyEngine,
    PolicyLevel,
    PolicyRequest,
)

REPO = "MAI-AMAN/VibeGuard"


def engine() -> PolicyEngine:
    return PolicyEngine(PolicyConfig(allowed_repositories=frozenset({REPO})))


def test_read_only_action_is_allowed() -> None:
    decision = engine().evaluate(PolicyRequest(repository=REPO, action=Action.OBSERVE))
    assert decision.allowed
    assert decision.level is PolicyLevel.READ_ONLY


def test_write_requires_approval() -> None:
    decision = engine().evaluate(
        PolicyRequest(repository=REPO, action=Action.COMMIT_FILES)
    )
    assert not decision.allowed
    assert decision.level is PolicyLevel.REQUIRES_APPROVAL


def test_approved_scoped_write_is_allowed() -> None:
    decision = engine().evaluate(
        PolicyRequest(
            repository=REPO,
            action=Action.COMMIT_FILES,
            approval_valid=True,
            changed_files=("src/vibeguard/main.py",),
            base_sha="a",
            approved_base_sha="a",
        )
    )
    assert decision.allowed


def test_dangerous_actions_are_forbidden_even_with_approval() -> None:
    for action in (
        Action.MERGE_PR,
        Action.FORCE_PUSH,
        Action.DELETE_RESOURCE,
        Action.DEPLOY_PRODUCTION,
        Action.MANIPULATE_CREDENTIALS,
    ):
        decision = engine().evaluate(
            PolicyRequest(repository=REPO, action=action, approval_valid=True)
        )
        assert not decision.allowed
        assert decision.level is PolicyLevel.FORBIDDEN


def test_scope_and_sensitive_paths_are_rejected() -> None:
    wrong_sha = engine().evaluate(
        PolicyRequest(
            repository=REPO,
            action=Action.APPLY_PATCH,
            approval_valid=True,
            base_sha="new",
            approved_base_sha="approved",
        )
    )
    secret = engine().evaluate(
        PolicyRequest(
            repository=REPO,
            action=Action.APPLY_PATCH,
            approval_valid=True,
            changed_files=(".env",),
        )
    )
    assert not wrong_sha.allowed
    assert not secret.allowed


def test_non_allowlisted_repository_is_rejected() -> None:
    decision = engine().evaluate(
        PolicyRequest(repository="someone/other", action=Action.OBSERVE)
    )
    assert not decision.allowed
