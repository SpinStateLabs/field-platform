"""Direct unit tests for ``usage.evaluate_rogue`` (scout proposal P-6).

The function is pure, so no HTTP and no store. The burst boundary is ``>=``
(usage.py, README: ``>= token_rate_limit``): exactly the limit fires. The
Field text says "before rogue_burst", which is ambiguous; these tests pin the
shipped behaviour, they do not argue for it.
"""
from __future__ import annotations

import pytest

from spend_governor.usage import RogueKind, UsagePolicy, evaluate_rogue

LIMIT = 5000


def _policy(allowed=None, limit=LIMIT) -> UsagePolicy:
    return UsagePolicy(agent_id="a1", allowed_models=allowed or [], token_rate_limit=limit)


def _kinds(findings):
    return [f.kind for f in findings]


def test_burst_below_the_limit_does_not_fire():
    assert evaluate_rogue(_policy(), "m", True, LIMIT - 1) == []


def test_burst_exactly_at_the_limit_fires():
    assert _kinds(evaluate_rogue(_policy(), "m", True, LIMIT)) == [RogueKind.ROGUE_BURST]


def test_burst_above_the_limit_fires():
    assert _kinds(evaluate_rogue(_policy(), "m", True, LIMIT + 1)) == [RogueKind.ROGUE_BURST]


def test_no_rate_limit_never_bursts():
    assert evaluate_rogue(_policy(limit=None), "m", True, 10**12) == []


def test_policy_none_and_priced_gives_nothing():
    assert evaluate_rogue(None, "m", True, 10**9) == []


def test_unpriced_fires_even_without_a_policy():
    assert _kinds(evaluate_rogue(None, "m", False, 0)) == [RogueKind.UNPRICED]


def test_empty_allow_list_never_fires_rogue_model():
    assert evaluate_rogue(_policy(allowed=[]), "anything", True, 0) == []


def test_model_outside_the_allow_list_fires_and_names_the_model():
    out = evaluate_rogue(_policy(allowed=["good"]), "bad", True, 0)
    assert _kinds(out) == [RogueKind.ROGUE_MODEL]
    assert "'bad'" in out[0].detail


def test_model_inside_the_allow_list_is_quiet():
    assert evaluate_rogue(_policy(allowed=["good"]), "good", True, 0) == []


def test_all_three_at_once_in_a_stable_order():
    out = evaluate_rogue(_policy(allowed=["good"]), "bad", False, LIMIT)
    assert _kinds(out) == [RogueKind.UNPRICED, RogueKind.ROGUE_MODEL, RogueKind.ROGUE_BURST]


@pytest.mark.parametrize("tokens", [LIMIT - 1, LIMIT, LIMIT + 1])
def test_burst_detail_names_tokens_window_and_limit(tokens):
    out = evaluate_rogue(_policy(), "m", True, tokens)
    if tokens >= LIMIT:
        d = out[0].detail
        assert str(tokens) in d and str(LIMIT) in d and "3600" in d
    else:
        assert out == []
