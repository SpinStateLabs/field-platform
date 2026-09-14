"""v1.2 D2b — drift keyed by (route, dimension): overall and sycophancy.

window_size=2, baseline_windows=2, band=0.15 throughout: four scores fix a
series' baseline, then two out-of-band windows (four scores) fire its alert.
Alert counts are exact per (route, dimension) — never `>= 1` / `any()`."""

from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream
from force_gateway.drift import DIMENSIONS, DriftTracker
from force_gateway.hygiene_judge import MockHygieneJudge

from test_gateway_delta import FakeGovernor, FakeLedger


def run(scores, judge=None, preset="analysis"):
    judge = judge or MockHygieneJudge(scores=scores)
    ledger = FakeLedger()
    client = TestClient(create_app(
        upstream=mock_upstream, governor_client=FakeGovernor(), ledger_client=ledger,
        hygiene_judge=judge, sample_every=1, latency_budget_ms=10_000.0,
        drift=DriftTracker(window_size=2, band=0.15, baseline_windows=2)))
    for _ in range(len(scores)):
        r = client.post("/v1/messages", json={"model": "m", "messages": []},
                        headers={"x-force-preset": preset})
        assert r.status_code == 200, r.text
    return client, ledger, judge


def alerts(ledger, dimension=None):
    found = [e["payload"] for e in ledger.events
             if e["event_type"] == "gateway.drift_alert"]
    return [a for a in found if dimension is None or a["dimension"] == dimension]


def test_dimensions_fed_are_overall_and_sycophancy():
    assert DIMENSIONS == ("overall", "sycophancy")


def test_sycophancy_drifts_while_overall_holds_exactly_one_sycophancy_alert():
    good = {"overall": 0.9, "sycophancy": 0.9}
    flattering = {"overall": 0.9, "sycophancy": 0.4}
    client, ledger, _ = run([good] * 4 + [flattering] * 4)
    assert len(alerts(ledger, "sycophancy")) == 1
    assert alerts(ledger, "overall") == []
    assert len(alerts(ledger)) == 1
    payload = alerts(ledger, "sycophancy")[0]
    assert (payload["route"], payload["baseline_mean"]) == ("analysis", 0.9)
    assert payload["window_means"] == [0.4, 0.4]
    t = client.get("/telemetry").json()
    assert t["active_alerts"] == [{"route": "analysis", "dimension": "sycophancy"}]
    assert t["hygiene_trend"]["analysis"]["overall"]["alerts_fired"] == 0
    assert t["hygiene_trend"]["analysis"]["sycophancy"]["alerts_fired"] == 1


def test_overall_drifts_while_sycophancy_holds_exactly_one_overall_alert():
    good = {"overall": 0.9, "sycophancy": 0.9}
    sloppy = {"overall": 0.4, "sycophancy": 0.9}
    client, ledger, _ = run([good] * 4 + [sloppy] * 4)
    assert len(alerts(ledger, "overall")) == 1
    assert alerts(ledger, "sycophancy") == []
    assert len(alerts(ledger)) == 1
    t = client.get("/telemetry").json()
    assert t["active_alerts"] == [{"route": "analysis", "dimension": "overall"}]


def test_baselines_are_independent_per_dimension():
    # sycophancy sits at 0.5 all along: far from overall's 0.9 baseline but
    # inside its OWN band — no alert for either series.
    steady = {"overall": 0.9, "sycophancy": 0.5}
    client, ledger, _ = run([steady] * 8)
    assert alerts(ledger) == []
    trend = client.get("/telemetry").json()["hygiene_trend"]["analysis"]
    assert trend["overall"]["baseline_mean"] == 0.9
    assert trend["sycophancy"]["baseline_mean"] == 0.5


def test_per_dimension_mock_scores_default_missing_dimensions_to_overall():
    judge = MockHygieneJudge(scores=[{"overall": 0.7}, {"overall": 0.6, "sycophancy": 0.2}])
    first, second = judge.judge("x", "analysis"), judge.judge("x", "analysis")
    assert (first.overall, first.sycophancy, first.premise_rigor) == (0.7, 0.7, 0.7)
    assert (second.overall, second.sycophancy, second.premise_rigor) == (0.6, 0.2, 0.6)


def test_model_change_resets_both_series():
    judge = MockHygieneJudge(scores=[0.9], model="judge-model-a")
    client, ledger, _ = run([0.9] * 4, judge=judge)
    trend = client.get("/telemetry").json()["hygiene_trend"]["analysis"]
    assert trend["overall"]["baseline_mean"] == trend["sycophancy"]["baseline_mean"] == 0.9

    judge.model = "judge-model-b"
    judge.scores = [0.2]
    r = client.post("/v1/messages", json={"model": "m", "messages": []})
    assert r.status_code == 200
    trend = client.get("/telemetry").json()["hygiene_trend"]["analysis"]
    for dimension in ("overall", "sycophancy"):
        st = trend[dimension]
        assert st["model"] == "judge-model-b", dimension
        assert st["baseline_mean"] is None and st["completed_windows"] == [], dimension
        assert st["scores_in_current_window"] == 1, dimension
    assert alerts(ledger) == []


def test_a_judge_change_on_one_series_resets_the_whole_route():
    tracker = DriftTracker(window_size=1, band=0.1, baseline_windows=1)
    for dimension in ("overall", "sycophancy"):
        tracker.record("analysis", dimension, 0.9, "model-a", "hygiene-v1")
    tracker.record("audit", "overall", 0.9, "model-a", "hygiene-v1")
    tracker.record("analysis", "overall", 0.3, "model-b", "hygiene-v1")
    st = tracker.status()
    assert st["analysis"]["sycophancy"]["model"] == "model-b"
    assert st["analysis"]["sycophancy"]["baseline_mean"] is None
    assert st["analysis"]["overall"]["baseline_mean"] == 0.3
    # another route's series is untouched
    assert st["audit"]["overall"]["model"] == "model-a"
    assert st["audit"]["overall"]["baseline_mean"] == 0.9


def test_rubric_change_resets_like_a_model_change():
    tracker = DriftTracker(window_size=1, band=0.1, baseline_windows=1)
    tracker.record("r", "sycophancy", 0.9, "m", "hygiene-v1")
    assert tracker.record("r", "sycophancy", 0.1, "m", "hygiene-v2") is None
    assert tracker.status()["r"]["sycophancy"]["baseline_mean"] == 0.1


def test_routes_are_separate_series():
    tracker = DriftTracker(window_size=1, band=0.1, baseline_windows=1)
    tracker.record("analysis", "overall", 0.9, "m", "v")
    tracker.record("audit", "overall", 0.2, "m", "v")
    assert tracker.record("analysis", "overall", 0.1, "m", "v") is None  # out #1
    alert = tracker.record("analysis", "overall", 0.1, "m", "v")        # out #2
    assert (alert.route, alert.dimension, alert.baseline_mean) == ("analysis", "overall", 0.9)
    assert tracker.active_alerts() == [{"route": "analysis", "dimension": "overall"}]
