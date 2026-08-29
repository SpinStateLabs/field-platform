"""S2 scorecard tests — gates, predicate coverage, determinism, report honesty.

The gate test runs the full 100-seed corpus through the real in-process stack
with the engine in LOG_ONLY (the served default), toggling `stack.ledger_up`
for the ledger-unreachable group. One module-scoped run is shared across the
assertion tests (the expired-token fixture costs a ~2 s real wait)."""

import time

import pytest

from conformance_sentinel.measure import (
    CATCH_GATE,
    FALSE_BLOCK_GATE,
    MeasurementError,
    build_meta,
    compute_metrics,
    render_json,
    render_markdown,
    run_suite,
)
from conformance_sentinel.mode import SentinelMode
from conformance_sentinel.routing import needs_semantic_judgment
from conformance_sentinel.seeded import SEED_SCOPE, build_corpus, provision
from tests.conftest import Stack


@pytest.fixture(scope="module")
def scorecard_run(tmp_path_factory):
    work = tmp_path_factory.mktemp("scorecard")
    stack = Stack(work)
    stack.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY
    fixtures = provision(registry=stack.registry, delegation=stack.delegation,
                         manifest_dir=work, wait=time.sleep)

    def check(seed):
        r = stack.sentinel.post("/check", json={
            "agent_id": fixtures.agent_id, "action": seed.action,
            "token_id": fixtures.tokens[seed.token_kind]})
        assert r.status_code == 200, r.text
        return r.json()

    results = run_suite(
        check, build_corpus(), mode="log_only",
        ledger_toggle=lambda down: setattr(stack, "ledger_up", not down))
    return compute_metrics(results)


def test_gates_pass_on_full_seeded_suite(scorecard_run):
    sc = scorecard_run
    assert sc.total_seeds == 100 and sc.run_seed_count == 100
    assert not sc.skipped_seed_ids
    assert sc.violation_count == 40 and sc.conforming_count == 53
    assert sc.gated_catch_rate >= CATCH_GATE, sc.gated_missed_ids
    assert sc.structural_false_block_rate <= FALSE_BLOCK_GATE, sc.false_block_ids
    assert sc.gates_passed


def test_semantic_gap_and_counts_reported(scorecard_run):
    sc = scorecard_run
    # Pre-judge, every ambiguous-conforming paraphrase would-blocks — the gap
    # the S3 judge exists to close. If this ever shrinks without a judge,
    # something changed in scope matching and needs a look.
    assert sc.ambiguous_conforming_count == 7
    assert len(sc.semantic_gap_blocked_ids) == 7
    assert sc.combined_false_block_rate > FALSE_BLOCK_GATE
    assert sc.would_have_blocked >= 40 + 7  # violations + semantic gap
    assert sc.would_have_escalated == 0  # seed manifest declares no triggers
    assert sc.tokens_per_judgment == 0
    assert "no semantic judge exists until S3" in sc.tokens_per_judgment_source


def test_routing_predicate_coverage_bidirectional():
    seeds = build_corpus()
    for seed in seeds:
        fired = needs_semantic_judgment(seed.action, SEED_SCOPE)
        assert fired == seed.routes_to_judge, (seed.seed_id, seed.action)
    routed = [s for s in seeds if s.routes_to_judge]
    assert len(routed) == 15 and len(seeds) == 100  # ~15% by mix design
    # structural categories never route
    assert all(s.category in ("ambiguous-violating", "ambiguous-conforming")
               for s in routed)


def test_corpus_deterministic():
    assert build_corpus() == build_corpus()


def test_measure_refuses_non_log_only_mode():
    with pytest.raises(MeasurementError, match="log-only"):
        run_suite(check=None, seeds=[], mode="enforce")


def test_measure_refuses_real_blocks(tmp_path):
    """A live enforce-mode estate that lies about its mode still gets caught:
    the first real BLOCK aborts the measurement."""
    stack = Stack(tmp_path)  # engine defaults ENFORCE
    fixtures = provision(registry=stack.registry, delegation=stack.delegation,
                         manifest_dir=tmp_path, wait=lambda s: None)

    def check(seed):
        r = stack.sentinel.post("/check", json={
            "agent_id": fixtures.agent_id, "action": seed.action,
            "token_id": fixtures.tokens[seed.token_kind]})
        return r.json()

    breach = [s for s in build_corpus() if s.category == "scope-breach"][:1]
    with pytest.raises(MeasurementError, match="not behaving log-only"):
        run_suite(check, breach, mode="log_only")


def test_report_carries_honesty_contract(scorecard_run):
    sc = scorecard_run
    meta = build_meta(runner="in-process", mode="log_only",
                      ledger_seeds_included=True, engine_commit="test")
    md = render_markdown(sc, meta)
    for required in (
        "(proposed; ratified at PoC exit)",
        "by construction",
        "do not measure detection power",
        "would fail if paraphrased-conforming actions were included",
        "S3 semantic judge",
        "mix-driven suite composition",
        "pending live telemetry",
        "Tokens/judgment | 0",
        "s2-fixtures-v1",
        "Gate granularity",
        "context.would_be",
    ):
        assert required in md, required
    js = render_json(sc, meta)
    assert '"gates_passed": true' in js
    assert '"fixture_version": "s2-fixtures-v1"' in js


def test_per_seed_table_complete(scorecard_run):
    sc = scorecard_run
    assert len(sc.rows) == 100
    by_id = {r["seed_id"]: r for r in sc.rows}
    assert by_id["SB-01"]["actual_would_be_clause"] == "D.scope"
    assert by_id["EXP-01"]["actual_would_be_clause"] == "D.expired"
    assert by_id["REV-01"]["actual_would_be_clause"] == "D.revoked"
    assert by_id["LU-01"]["actual_would_be_clause"] == "L.unreachable"
    assert by_id["AV-01"]["post_s3_expected"] == "ESCALATE"
    assert by_id["OK-01"]["actual_would_be_decision"] == "ALLOW"
    assert by_id["AC-01"]["actual_would_be_clause"] == "D.scope"  # semantic gap
