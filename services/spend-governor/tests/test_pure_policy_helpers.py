"""FALLBACK (no scout card): two pure spend-governor helpers that no test named, reached before only through the API.

* usage.evaluate_rogue: the rogue arithmetic for one usage event. Pinned: each kind alone, the burst boundary
  (`>=` the limit), no policy, no limit, an empty allow-list never fires rogue_model, the order of findings.
* core.window_action_rows: Option A precedence for one action's rolling window (sentinel-metered rows win when
  any exist, else the self-reported rows). Tests only; no source edit."""

from __future__ import annotations

import pytest

from spend_governor.core import window_action_rows
from spend_governor.usage import RogueKind, UsagePolicy, evaluate_rogue

MODEL = "claude-haiku-4-5"


def policy(**kw):
    kw.setdefault("agent_id", "a1")
    return UsagePolicy(**kw)


def kinds(findings):
    return [f.kind for f in findings]


# ---- evaluate_rogue ---------------------------------------------------------------------------------------


def test_a_priced_allowed_model_under_the_limit_is_clean():
    p = policy(allowed_models=[MODEL], token_rate_limit=1000)
    assert evaluate_rogue(p, MODEL, True, 999) == []


def test_no_policy_only_the_unpriced_check_applies():
    assert evaluate_rogue(None, MODEL, True, 10**12) == []
    assert kinds(evaluate_rogue(None, MODEL, False, 10**12)) == [RogueKind.UNPRICED]


@pytest.mark.parametrize("tokens,fires", [(999, False), (1000, True), (1001, True), (0, False)])
def test_the_burst_boundary_is_greater_or_equal(tokens, fires):
    p = policy(token_rate_limit=1000, rate_window_seconds=60)
    got = evaluate_rogue(p, MODEL, True, tokens)
    if fires:
        assert kinds(got) == [RogueKind.ROGUE_BURST]
        assert f"{tokens} tokens in the last 60s >= limit 1000" in got[0].detail
    else:
        assert got == []


def test_no_token_limit_never_bursts():
    assert evaluate_rogue(policy(token_rate_limit=None), MODEL, True, 10**15) == []


def test_an_empty_allow_list_never_flags_a_model():
    assert evaluate_rogue(policy(allowed_models=[]), "anything-at-all", True, 0) == []


def test_a_model_outside_the_allow_list_is_rogue_and_the_detail_names_it():
    got = evaluate_rogue(policy(allowed_models=[MODEL]), "claude-opus-5", True, 0)
    assert kinds(got) == [RogueKind.ROGUE_MODEL]
    assert "claude-opus-5" in got[0].detail and MODEL in got[0].detail


def test_the_allow_list_match_is_exact():
    p = policy(allowed_models=[MODEL])
    for near in (MODEL.upper(), MODEL + " ", MODEL[:-1]):
        assert kinds(evaluate_rogue(p, near, True, 0)) == [RogueKind.ROGUE_MODEL], near


def test_every_finding_at_once_comes_back_in_a_fixed_order():
    p = policy(allowed_models=[MODEL], token_rate_limit=10)
    got = evaluate_rogue(p, "unknown-model", False, 10)
    assert kinds(got) == [RogueKind.UNPRICED, RogueKind.ROGUE_MODEL, RogueKind.ROGUE_BURST]
    assert "unknown-model" in got[0].detail and "no price" in got[0].detail


# ---- window_action_rows -----------------------------------------------------------------------------------

SELF = [("2026-11-04T10:00:00+00:00", "self", 2), ("2026-11-04T10:01:00+00:00", "self", 3)]
METERED = [("2026-11-04T10:00:30+00:00", "sentinel", 1)]


def test_self_reported_rows_alone_are_all_counted():
    assert window_action_rows(SELF) == [(SELF[0][0], 2), (SELF[1][0], 3)]


def test_metered_rows_alone_are_all_counted():
    assert window_action_rows(METERED) == [(METERED[0][0], 1)]


def test_when_any_metered_row_exists_the_self_reported_rows_are_dropped():
    got = window_action_rows(SELF + METERED)
    assert got == [(METERED[0][0], 1)]
    assert window_action_rows(METERED + SELF) == got                 # input order does not matter for the choice


def test_any_non_sentinel_source_counts_as_self_reported():
    rows = [("t1", "self", 1), ("t2", "console", 4), ("t3", "", 5)]
    assert window_action_rows(rows) == [("t1", 1), ("t2", 4), ("t3", 5)]


def test_the_order_of_the_kept_rows_is_the_input_order():
    rows = [("t3", "sentinel", 3), ("t1", "sentinel", 1), ("t2", "sentinel", 2)]
    assert window_action_rows(rows) == [("t3", 3), ("t1", 1), ("t2", 2)]


def test_no_rows_is_empty_and_a_generator_is_accepted():
    assert window_action_rows([]) == []
    assert window_action_rows(r for r in SELF) == [(SELF[0][0], 2), (SELF[1][0], 3)]
