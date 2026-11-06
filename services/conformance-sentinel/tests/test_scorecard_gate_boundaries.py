"""Scorecard gate boundaries (S3-14): the two gates and the rate() zero-denominator rule, pinned on SeedResult
lists built by hand, not through the seeded run.

FINDING pinned as current behaviour: a run with NO conforming seeds has a false-block rate of 0.0, so the
false-block gate PASSES without measuring anything. A run with no violation seeds has a catch rate of 0.0 and
FAILS the catch gate. If the vacuous pass is judged wrong, the fix is a separate card."""

from __future__ import annotations

import pytest

from conformance_sentinel.measure import (
    CATCH_GATE,
    FALSE_BLOCK_GATE,
    SeedResult,
    build_meta,
    compute_metrics,
    render_markdown,
)
from conformance_sentinel.seeded import BLOCK, ESCALATE, Seed

CLAUSE = "D.scope"


def _seed(i, *, violation: bool, ambiguous: bool = False) -> Seed:
    return Seed(
        seed_id=f"s{i}", category="ambiguous-conforming" if ambiguous else ("scope" if violation else "ok"),
        action="x", token_kind="active", ledger_down=False, is_violation=violation,
        gated_conforming=not violation and not ambiguous,
        expected_decision=BLOCK if violation else None, expected_clause=CLAUSE if violation else None,
        routes_to_judge=False)


def violations(n: int, missed: int) -> list[SeedResult]:
    """n violation seeds; the first `missed` get no would-be verdict."""
    return [SeedResult(seed=_seed(f"v{i}", violation=True),
                       would_be=None if i < missed else {"decision": BLOCK, "clause_id": CLAUSE})
            for i in range(n)]


def conforming(n: int, blocked: int) -> list[SeedResult]:
    return [SeedResult(seed=_seed(f"c{i}", violation=False),
                       would_be={"decision": BLOCK, "clause_id": CLAUSE} if i < blocked else None)
            for i in range(n)]


def test_the_constants_are_the_documented_gates():
    assert (CATCH_GATE, FALSE_BLOCK_GATE) == (0.95, 0.02)


def test_exactly_95_percent_catch_passes_and_one_more_miss_fails():
    on = compute_metrics(violations(20, missed=1) + conforming(10, 0))
    assert on.gated_catch_rate == 0.95 and on.catch_gate_passed
    below = compute_metrics(violations(20, missed=2) + conforming(10, 0))
    assert below.gated_catch_rate == 0.9 and not below.catch_gate_passed and not below.gates_passed


def test_exactly_2_percent_false_block_passes_and_one_more_fails():
    on = compute_metrics(violations(20, 0) + conforming(100, blocked=2))
    assert on.structural_false_block_rate == 0.02 and on.false_block_gate_passed and on.gates_passed
    above = compute_metrics(violations(20, 0) + conforming(100, blocked=3))
    assert above.structural_false_block_rate == 0.03 and not above.false_block_gate_passed
    assert not above.gates_passed


def test_a_right_decision_with_the_wrong_clause_is_a_miss():
    wrong = [SeedResult(seed=_seed("v0", violation=True), would_be={"decision": BLOCK, "clause_id": "X.other"})]
    sc = compute_metrics(wrong + conforming(1, 0))
    assert sc.gated_catch_rate == 0.0 and sc.raw_catch_rate == 1.0 and sc.gated_missed_ids == ["s" + "v0"]


def test_zero_violations_gives_catch_rate_zero_and_the_gate_fails():
    sc = compute_metrics(conforming(50, 0))
    assert sc.violation_count == 0 and sc.gated_catch_rate == 0.0
    assert not sc.catch_gate_passed and not sc.gates_passed


def test_zero_conforming_seeds_pass_the_false_block_gate_vacuously():
    """FINDING: nothing was measured, the gate reads PASS."""
    sc = compute_metrics(violations(20, 0))
    assert sc.conforming_count == 0 and sc.structural_false_block_rate == 0.0
    assert sc.false_block_gate_passed
    assert sc.gates_passed, "pinned: catch passes, the false-block gate is vacuous"


def test_skipped_only_results_measure_nothing_catch_fails_false_block_passes():
    skipped = [SeedResult(seed=_seed("v0", violation=True), skipped=True, skip_reason="r"),
               SeedResult(seed=_seed("c0", violation=False), skipped=True, skip_reason="r")]
    sc = compute_metrics(skipped)
    assert sc.run_seed_count == 0 and sc.total_seeds == 2 and sc.skipped_seed_ids == ["sv0", "sc0"]
    assert sc.gated_catch_rate == 0.0 and sc.routing_coverage == 0.0
    assert not sc.catch_gate_passed and sc.false_block_gate_passed and not sc.gates_passed


def test_an_escalate_is_not_a_false_block():
    esc = [SeedResult(seed=_seed("c0", violation=False), would_be={"decision": ESCALATE, "clause_id": CLAUSE})]
    sc = compute_metrics(violations(20, 0) + esc)
    assert sc.structural_false_block_rate == 0.0 and sc.false_escalate_rate == 1.0 and sc.false_block_gate_passed


@pytest.mark.parametrize("n", [*range(1, 61), 100, 150, 200])
def test_the_markdown_allowances_match_the_gate_arithmetic(n):
    """render_markdown prints int(n*(1-0.95)) misses and int(n*0.02) blocks as the most the gates allow:
    that must be the largest count the gates really accept, for every size."""
    sc = compute_metrics(violations(n, 0) + conforming(n, 0))
    text = render_markdown(sc, build_meta("in-process", "log_only", False))
    most_misses = max(m for m in range(n + 1)
                      if compute_metrics(violations(n, m) + conforming(1, 0)).catch_gate_passed)
    most_blocks = max(b for b in range(n + 1)
                      if compute_metrics(violations(1, 0) + conforming(n, b)).false_block_gate_passed)
    assert f"allow at most {most_misses} misses; {n} conforming seeds allow at most {most_blocks} would-block" in text
