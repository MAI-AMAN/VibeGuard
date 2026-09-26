"""Explicit, fail-closed VibeGuard workflow state machine."""

from enum import StrEnum


class State(StrEnum):
    IDLE = "IDLE"
    OBSERVING = "OBSERVING"
    ANALYZING = "ANALYZING"
    COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
    REPRODUCING = "REPRODUCING"
    WAITING_FOR_REMEDIATION_APPROVAL = "WAITING_FOR_REMEDIATION_APPROVAL"
    GENERATING_PATCH = "GENERATING_PATCH"
    WAITING_FOR_PATCH_APPROVAL = "WAITING_FOR_PATCH_APPROVAL"
    VERIFYING = "VERIFYING"
    WAITING_FOR_SHIPMENT_APPROVAL = "WAITING_FOR_SHIPMENT_APPROVAL"
    SHIPPING = "SHIPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TRANSITIONS: dict[State, frozenset[State]] = {
    State.IDLE: frozenset({State.OBSERVING, State.FAILED}),
    State.OBSERVING: frozenset({State.ANALYZING, State.FAILED}),
    State.ANALYZING: frozenset(
        {State.COLLECTING_EVIDENCE, State.COMPLETED, State.FAILED}
    ),
    State.COLLECTING_EVIDENCE: frozenset({State.REPRODUCING, State.FAILED}),
    State.REPRODUCING: frozenset(
        {State.WAITING_FOR_REMEDIATION_APPROVAL, State.FAILED}
    ),
    State.WAITING_FOR_REMEDIATION_APPROVAL: frozenset(
        {State.GENERATING_PATCH, State.FAILED}
    ),
    State.GENERATING_PATCH: frozenset({State.WAITING_FOR_PATCH_APPROVAL, State.FAILED}),
    State.WAITING_FOR_PATCH_APPROVAL: frozenset({State.VERIFYING, State.FAILED}),
    State.VERIFYING: frozenset({State.WAITING_FOR_SHIPMENT_APPROVAL, State.FAILED}),
    State.WAITING_FOR_SHIPMENT_APPROVAL: frozenset({State.SHIPPING, State.FAILED}),
    State.SHIPPING: frozenset({State.COMPLETED, State.FAILED}),
    State.COMPLETED: frozenset(),
    State.FAILED: frozenset(),
}


def can_transition(current: State, target: State) -> bool:
    return target in TRANSITIONS[current]


def transition(current: State, target: State) -> State:
    if not can_transition(current, target):
        raise ValueError(
            f"Illegal VibeGuard transition: {current.value} -> {target.value}"
        )
    return target
