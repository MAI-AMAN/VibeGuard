from itertools import pairwise

import pytest

from vibeguard.workflow.states import State, can_transition, transition

HAPPY_PATH = [
    State.IDLE,
    State.OBSERVING,
    State.ANALYZING,
    State.COLLECTING_EVIDENCE,
    State.REPRODUCING,
    State.WAITING_FOR_REMEDIATION_APPROVAL,
    State.GENERATING_PATCH,
    State.WAITING_FOR_PATCH_APPROVAL,
    State.VERIFYING,
    State.WAITING_FOR_SHIPMENT_APPROVAL,
    State.SHIPPING,
    State.COMPLETED,
]


def test_happy_path_transitions_are_allowed() -> None:
    for current, target in pairwise(HAPPY_PATH):
        assert can_transition(current, target)
        assert transition(current, target) is target


def test_all_nonterminal_states_can_fail() -> None:
    for state in State:
        if state not in {State.COMPLETED, State.FAILED}:
            assert can_transition(state, State.FAILED)


def test_approval_states_cannot_be_skipped() -> None:
    assert not can_transition(State.REPRODUCING, State.GENERATING_PATCH)
    assert not can_transition(State.GENERATING_PATCH, State.VERIFYING)
    assert not can_transition(State.VERIFYING, State.SHIPPING)


def test_invalid_transition_raises() -> None:
    with pytest.raises(ValueError, match="Illegal"):
        transition(State.IDLE, State.SHIPPING)


def test_terminal_states_are_terminal() -> None:
    assert not any(can_transition(State.COMPLETED, target) for target in State)
    assert not any(can_transition(State.FAILED, target) for target in State)
