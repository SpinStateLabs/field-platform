"""S8-21 — measure.run_suite turns a failing ledger-toggle command and a wrong-shaped /check verdict
into MeasurementError (the CLI's existing 'measurement refused' exit 1), never a traceback. The error
names the exception TYPE only, never the command or its output. compute_metrics tolerates a hand-built
SeedResult whose would_be is not a dict."""

from __future__ import annotations

import subprocess

import pytest

from conformance_sentinel.measure import MeasurementError, SeedResult, compute_metrics, run_suite
from conformance_sentinel.seeded import build_corpus

CORPUS = build_corpus()
UP = next(s for s in CORPUS if not s.ledger_down)
DOWN = next(s for s in CORPUS if s.ledger_down)
SECRET = "SECRET-COMMAND-OUTPUT-MUST-NOT-LEAK"


def ok_check(seed):
    return {"decision": "ALLOW", "context": {"would_be": None}}


# --- the ledger toggle -------------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [
    subprocess.CalledProcessError(1, f"docker stop {SECRET}", output=SECRET, stderr=SECRET),
    OSError(f"no such file {SECRET}"),
    RuntimeError(SECRET),
    subprocess.TimeoutExpired(f"cmd {SECRET}", 5),
], ids=lambda e: type(e).__name__)
def test_a_failing_toggle_down_is_a_measurement_error_naming_only_the_type(exc):
    def toggle(down):
        raise exc

    with pytest.raises(MeasurementError) as info:
        run_suite(ok_check, [DOWN], mode="log_only", ledger_toggle=toggle)
    assert type(exc).__name__ in str(info.value)
    assert SECRET not in str(info.value) and "docker" not in str(info.value)


def test_a_failing_toggle_back_up_is_a_measurement_error_and_the_finally_retries():
    calls: list[bool] = []

    def toggle(down):
        calls.append(down)
        if down is False and calls.count(False) == 1:
            raise subprocess.CalledProcessError(1, "up")

    with pytest.raises(MeasurementError, match="CalledProcessError"):
        run_suite(ok_check, [DOWN, UP], mode="log_only", ledger_toggle=toggle)
    assert calls == [True, False, False]          # the cleanup tried again to bring the ledger up


def test_a_working_toggle_is_unchanged():
    calls = []
    res = run_suite(ok_check, [UP, DOWN, UP], mode="log_only", ledger_toggle=calls.append)
    assert calls == [True, False] and [r.skipped for r in res] == [False, False, False]


# --- the verdict -------------------------------------------------------------------------------------

@pytest.mark.parametrize("verdict", [[], "ALLOW", 5, None, ["decision"],
                                     {"decision": "ALLOW", "context": []},
                                     {"decision": "ALLOW", "context": "x"},
                                     {"decision": "ALLOW", "context": {"would_be": "BLOCK"}},
                                     {"decision": "ALLOW", "context": {"would_be": ["BLOCK"]}}],
                         ids=repr)
def test_a_wrong_shaped_verdict_is_a_measurement_error(verdict):
    with pytest.raises(MeasurementError, match="wrong-shaped verdict"):
        run_suite(lambda seed: verdict, [UP], mode="log_only")


@pytest.mark.parametrize("verdict", [{"decision": "ALLOW"}, {"decision": "ALLOW", "context": None},
                                     {"decision": "ALLOW", "context": {}},
                                     {"decision": "ALLOW", "context": {"would_be": None, "shadowed": True}},
                                     {"decision": "ALLOW", "context": {"would_be": {"decision": "BLOCK",
                                                                                      "clause_id": "D.scope"}}}],
                         ids=repr)
def test_a_well_shaped_verdict_still_scores(verdict):
    (r,) = run_suite(lambda seed: verdict, [UP], mode="log_only")
    assert r.decision == "ALLOW"


def test_a_real_block_is_still_the_existing_refusal():
    with pytest.raises(MeasurementError, match="not behaving log-only"):
        run_suite(lambda seed: {"decision": "BLOCK"}, [UP], mode="log_only")


# --- compute_metrics ---------------------------------------------------------------------------------

@pytest.mark.parametrize("would_be", ["BLOCK", ["BLOCK"], 5, True])
def test_compute_metrics_tolerates_a_non_dict_would_be(would_be):
    result = SeedResult(seed=UP, decision="ALLOW", would_be=would_be)
    compute_metrics([result])                      # must not raise AttributeError
