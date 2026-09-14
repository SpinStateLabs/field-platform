"""v1.2 D2c — the persistent GatewayStore.

A second create_app on the same data dir is a restart: counts, rates,
baselines, the sampling stride and alert state resume; bypass_remaining does
not (a restart re-arms). A store fault is an instrumentation fault: traffic
answers 200 and the gateway bypasses, visibly."""

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream
from force_gateway.drift import DriftTracker
from force_gateway.hygiene_judge import MockHygieneJudge
from force_gateway.store import GatewayStore, data_path

from test_gateway_delta import FakeGovernor, FakeLedger


def app_on_disk(judge=None, ledger=None, sample_every=2, upstream=None, **kw):
    kw.setdefault("latency_budget_ms", 10_000.0)
    return create_app(
        upstream=upstream or mock_upstream, governor_client=FakeGovernor(),
        ledger_client=ledger if ledger is not None else FakeLedger(),
        hygiene_judge=judge, sample_every=sample_every,
        drift=DriftTracker(window_size=2, band=0.15, baseline_windows=2), **kw)


def post(client, n=1, **headers):
    for _ in range(n):
        r = client.post("/v1/messages", json={"model": "m", "messages": []},
                        headers=headers)
        assert r.status_code == 200, r.text


def drift_alerts(ledger):
    return [e for e in ledger.events if e["event_type"] == "gateway.drift_alert"]


def test_store_lives_under_field_data_dir(tmp_path):
    app = app_on_disk()
    post(TestClient(app))
    expected = tmp_path / "data" / "gateway" / "telemetry.sqlite3"
    assert data_path() == expected
    assert app.state.store.path == expected and expected.is_file()


def test_restart_resumes_counts_baselines_stride_and_alert_state():
    # Run 1: stride 2 => judged on requests 2,4,...,16: 4 baseline scores then
    # 4 bad ones => one alert per dimension; request 17 is not sampled.
    judge1 = MockHygieneJudge(scores=[0.9] * 4 + [0.4] * 4)
    ledger1 = FakeLedger()
    app1 = app_on_disk(judge=judge1, ledger=ledger1)
    c1 = TestClient(app1)
    post(c1, 17)
    assert len(judge1.calls) == 8 and len(drift_alerts(ledger1)) == 2
    before = c1.get("/telemetry").json()
    app1.state.store.close()  # the process ends

    judge2 = MockHygieneJudge(scores=[0.4])
    ledger2 = FakeLedger()
    app2 = app_on_disk(judge=judge2, ledger=ledger2)
    c2 = TestClient(app2)
    after = c2.get("/telemetry").json()
    for key in ("total_requests", "by_preset", "responses_with_confidence_tags",
                "total_output_tokens", "rates", "hygiene_trend", "active_alerts"):
        assert after[key] == before[key], key
    assert after["active_alerts"] == [{"route": "analysis", "dimension": "overall"},
                                      {"route": "analysis", "dimension": "sycophancy"}]
    for key in ("instrumented", "judged_samples", "judge_bypassed", "passthrough"):
        assert after["coverage"][key] == before["coverage"][key], key
    assert after["coverage"]["instrumented"] == 17
    assert [r["ts"] for r in after["recent"]] == [r["ts"] for r in before["recent"]]
    assert ledger2.events == []  # replay re-ledgers nothing

    # Stride resumed: request 18 is the next sampled one (a fresh counter
    # would have judged request 2 of the new process instead).
    post(c2)
    assert len(judge2.calls) == 1
    post(c2)
    assert len(judge2.calls) == 1
    # Alert state resumed: still-bad windows do not re-fire the episode.
    post(c2, 4)
    assert drift_alerts(ledger2) == []
    t = c2.get("/telemetry").json()
    assert t["hygiene_trend"]["analysis"]["overall"]["alerts_fired"] == 1
    assert t["total_requests"] == 23


def _judge_bypass_setup(reason):
    """(governor, judge) that make the one sampled request skip its judgment
    for `reason` (`judge_bypassed.<reason>`)."""
    if reason == "no_governor":
        return None, MockHygieneJudge()
    if reason == "governor_unreachable":
        return FakeGovernor(raise_get=True), MockHygieneJudge()
    if reason == "no_cap":
        return FakeGovernor(status_code=404), MockHygieneJudge()
    if reason == "governor_error":
        return FakeGovernor(status_code=500), MockHygieneJudge()
    if reason == "budget":
        return FakeGovernor(state="BLOCK"), MockHygieneJudge()
    return FakeGovernor(), MockHygieneJudge(raise_error=RuntimeError("synthetic judge failure"))


@pytest.mark.parametrize("reason", ["error", "budget", "no_cap", "governor_error",
                                    "governor_unreachable", "no_governor"])
def test_restart_resumes_passthrough_and_every_judge_bypass_reason(reason):
    gov, judge = _judge_bypass_setup(reason)
    app1 = create_app(upstream=mock_upstream, governor_client=gov, hygiene_judge=judge,
                      ledger_client=FakeLedger(), sample_every=1,
                      latency_budget_ms=10_000.0)
    c1 = TestClient(app1)
    post(c1)  # sampled; the judgment is skipped for `reason`
    post(c1, **{"x-force-passthrough": "judge"})  # secretless: honoured
    assert app1.state.coverage["judge_bypassed"] == {reason: 1}
    assert app1.state.coverage["passthrough"] == 1
    app1.state.store.close()  # the process ends

    cov = TestClient(app_on_disk()).get("/telemetry").json()["coverage"]
    assert cov["judge_bypassed"] == {reason: 1}
    assert cov["passthrough"] == 1
    assert cov["instrumented"] == 1


def test_lifespan_closes_an_owned_store_but_never_an_injected_one(tmp_path):
    owned = app_on_disk()
    with TestClient(owned) as client:
        post(client)
    with pytest.raises(sqlite3.ProgrammingError):
        owned.state.store.counters()  # closed at shutdown (Windows file locks)

    injected = GatewayStore(tmp_path / "injected.sqlite3")
    with TestClient(app_on_disk(store=injected)) as client:
        post(client)
    assert injected.counters()["request_count"] == 1  # the caller still owns it


class FlakyCommits:
    """`store.commit_request` whose listed call numbers raise a sqlite error."""

    def __init__(self, store, failing_calls):
        self.real = store.commit_request
        self.failing = set(failing_calls)
        self.calls = 0
        store.commit_request = self

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.failing:
            raise sqlite3.OperationalError("disk I/O error (synthetic)")
        return self.real(*args, **kwargs)


def test_a_failed_commit_leaves_memory_equal_to_the_store_and_health_recovers():
    """A commit that fails after a sampled judgment must not leave the
    in-memory stride or coverage ahead of the persisted values (a restart
    would disagree), and /health stops reporting `error` once a later commit
    succeeds."""
    judge = MockHygieneJudge(scores=[0.9])
    gov = FakeGovernor()
    app = create_app(upstream=mock_upstream, governor_client=gov, hygiene_judge=judge,
                     ledger_client=FakeLedger(), sample_every=2, bypass_cooldown=0,
                     latency_budget_ms=10_000.0,
                     drift=DriftTracker(window_size=2, band=0.15, baseline_windows=2))
    store = app.state.store
    FlakyCommits(store, failing_calls={2})
    client = TestClient(app)

    post(client)  # stride 1: not sampled, committed
    post(client)  # stride 2: judged, then the commit FAILS -> store_fault
    assert app.state.coverage["bypass_reasons"] == {"store_fault": 1}
    assert client.get("/health").json()["telemetry_store"] == "error"
    post(client)  # stride 2 again (nothing was committed): judged, committed
    post(client)  # stride 3: not sampled, committed
    assert len(judge.calls) == 2
    # The lost judgment's spend really happened, so it is still metered.
    assert [p["agent_id"] for _, p in gov.posts] == ["force-gateway", "force-gateway"]
    assert client.get("/health").json()["telemetry_store"] == "ok"

    persisted = store.counters()
    assert app.state.request_count == persisted["request_count"] == 3
    assert app.state.coverage["judged_samples"] == persisted["coverage.judged_samples"] == 1
    assert client.get("/telemetry").json()["total_requests"] == 3
    memory = {k: (dict(v) if isinstance(v, dict) else v)
              for k, v in app.state.coverage.items()}
    trend = app.state.drift.status()
    assert trend["analysis"]["overall"]["scores_in_current_window"] == 1
    store.close()

    restarted = app_on_disk(judge=MockHygieneJudge(), sample_every=2, bypass_cooldown=0)
    assert restarted.state.request_count == 3
    assert restarted.state.coverage == memory
    assert restarted.state.drift.status() == trend


def test_recovery_after_restart_rearms_from_the_replayed_baseline():
    app1 = app_on_disk(judge=MockHygieneJudge(scores=[0.9] * 4 + [0.4] * 4), sample_every=1)
    post(TestClient(app1), 8)
    app1.state.store.close()
    ledger = FakeLedger()
    app2 = app_on_disk(judge=MockHygieneJudge(scores=[0.9] * 2 + [0.4] * 4),
                       ledger=ledger, sample_every=1)
    c2 = TestClient(app2)
    post(c2, 2)  # a window back in band: re-armed
    assert c2.get("/telemetry").json()["active_alerts"] == []
    post(c2, 4)  # a NEW episode fires once per dimension
    assert [a["payload"]["dimension"] for a in drift_alerts(ledger)] == ["overall", "sycophancy"]


def test_bypass_remaining_is_not_persisted_but_the_gap_is():
    app1 = app_on_disk(latency_budget_ms=-1.0, bypass_cooldown=3)
    c1 = TestClient(app1)
    post(c1)
    assert c1.get("/telemetry").json()["coverage"]["bypass_remaining"] == 3
    post(c1)  # bypassed
    app1.state.store.close()
    c2 = TestClient(app_on_disk())
    cov = c2.get("/telemetry").json()["coverage"]
    assert cov["bypass_remaining"] == 0
    assert (cov["bypass_entries"], cov["bypass_reasons"], cov["bypassed"]) == (
        1, {"latency_budget": 1}, 1)
    assert c2.get("/health").json()["bypass_remaining"] == 0


def test_two_data_dirs_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "estate-a"))
    post(TestClient(app_on_disk()), 3)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "estate-b"))
    b = TestClient(app_on_disk())
    assert b.get("/telemetry").json()["total_requests"] == 0
    post(b)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "estate-a"))
    assert TestClient(app_on_disk()).get("/telemetry").json()["total_requests"] == 3


def test_an_injected_store_is_used_and_replayed(tmp_path):
    store = GatewayStore(tmp_path / "custom.sqlite3", retain=5)
    post(TestClient(app_on_disk(store=store)), 2)
    again = TestClient(app_on_disk(store=store))
    assert again.get("/telemetry").json()["total_requests"] == 2
    assert not data_path().exists()


def _spy():
    seen = []

    def upstream(body, headers):
        seen.append(body)
        return mock_upstream(body, headers)

    return seen, upstream


def test_corrupt_store_serves_200_and_bypasses_visibly():
    path = data_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this is not a sqlite database" * 64)
    seen, upstream = _spy()
    ledger = FakeLedger()
    client = TestClient(app_on_disk(upstream=upstream, ledger=ledger, bypass_cooldown=1))
    assert client.get("/health").json()["telemetry_store"] == "unavailable"

    post(client)  # instrumented attempt: store fault -> 200 + bypass
    post(client)  # bypassed: forwarded uninstrumented
    post(client)  # re-armed: faults again
    assert str(seen[0]["system"]).startswith("# FORCE Runtime Protocol")
    assert "system" not in seen[1]
    assert [e["payload"]["reason"] for e in ledger.events
            if e["event_type"] == "gateway.bypass"] == ["store_fault", "store_fault"]

    r = client.get("/telemetry")
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "telemetry store unavailable"
    assert detail["coverage"]["bypass_reasons"] == {"store_fault": 2}
    assert detail["coverage"]["bypassed"] == 1
    assert path.read_bytes().startswith(b"this is not a sqlite database")


def test_store_fault_mid_life_bypasses_and_telemetry_says_so():
    app = app_on_disk()
    client = TestClient(app)
    post(client)
    app.state.store.close()  # the file handle goes away under the service
    post(client)
    assert app.state.coverage["bypass_reasons"] == {"store_fault": 1}
    assert client.get("/telemetry").status_code == 503
    assert client.get("/health").json()["telemetry_store"] == "error"


def test_persisted_records_hold_no_response_text():
    post(TestClient(app_on_disk()), 2)
    raw = data_path().read_bytes()
    assert b"Appendix B" not in raw and b"timesheet CSV" not in raw
    assert b"force-gateway-mock" in raw  # the metadata is there


def test_retain_env_is_read_by_the_default_store(monkeypatch):
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "2")
    app = app_on_disk(telemetry_window=1)  # rows kept = max(retain, window)
    assert app.state.store.retain == 2
    post(TestClient(app), 4)
    assert len(app.state.store.records()) == 2
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "junk")
    assert GatewayStore(os.path.join(str(data_path().parent), "other.sqlite3")).retain == 10_000


def test_a_failed_commit_never_feeds_the_drift_tracker():
    """Scores are persisted BEFORE the in-memory tracker sees them, so the
    tracker can never hold a score a restart's replay would not reproduce."""
    ledger = FakeLedger()
    app = app_on_disk(judge=MockHygieneJudge(scores=[0.9]), ledger=ledger, sample_every=1)
    client = TestClient(app)
    app.state.store.close()
    post(client)
    assert app.state.coverage["bypass_reasons"] == {"store_fault": 1}
    assert app.state.drift.status() == {}
