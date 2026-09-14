"""ADR 10 delta tests — sampled hygiene judge, trend alerts, fail-open + capped.

Control-flow guarantees proven against deterministic fakes (judge scoring
quality stays Declared pending the quarterly human calibration; README)."""

import pytest
from fastapi.testclient import TestClient

from field_core.validation import validate_manifest_data

from force_gateway.api import create_app, mock_upstream
from force_gateway.drift import DriftTracker
from force_gateway.hygiene_judge import (
    HYGIENE_JUDGE_MODEL_DEFAULT,
    MockHygieneJudge,
    resolve_hygiene_judge,
    resolve_sample_every,
)
from force_gateway.self_manifest import (
    SELF_AGENT_ID,
    load_self_manifest,
)

OBSERVER_VERBS = ("inject", "observe", "invoke", "append")


class FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class FakeGovernor:
    """get(/status) configurable; post(/usage|/spend) recorded."""

    def __init__(self, status_code=200, state="OK", raise_get=False):
        self.status_code = status_code
        self.state = state
        self.raise_get = raise_get
        self.posts = []

    def get(self, path):
        if self.raise_get:
            raise ConnectionError("governor down")
        return FakeResp(self.status_code, {"state": self.state})

    def post(self, path, json=None):
        self.posts.append((path, json))
        return FakeResp(201)


class FakeLedger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append({"event_type": event_type, "payload": payload,
                            "agent_id": agent_id})


def make_client(judge=None, sample_every=1, governor=None, ledger=None,
                upstream=None, drift=None, latency_budget_ms=10_000.0,
                bypass_cooldown=2):
    app = create_app(
        upstream=upstream or mock_upstream, governor_client=governor,
        ledger_client=ledger, hygiene_judge=judge, sample_every=sample_every,
        drift=drift or DriftTracker(window_size=2, band=0.15, baseline_windows=2),
        latency_budget_ms=latency_budget_ms, bypass_cooldown=bypass_cooldown)
    return TestClient(app)


def call(client, body=None):
    r = client.post("/v1/messages", json=body or {"model": "m", "messages": []})
    assert r.status_code == 200, r.text
    return r


# --- flags: default off, fail-safe fallbacks ---

def test_judge_flag_defaults_and_fallback(monkeypatch):
    monkeypatch.delenv("FORCE_HYGIENE_JUDGE", raising=False)
    assert resolve_hygiene_judge() is None
    monkeypatch.setenv("FORCE_HYGIENE_JUDGE", "gpt")  # unknown -> OFF
    assert resolve_hygiene_judge() is None
    monkeypatch.setenv("FORCE_HYGIENE_JUDGE", "mock")
    assert isinstance(resolve_hygiene_judge(), MockHygieneJudge)


def test_sample_every_parsing(monkeypatch):
    monkeypatch.delenv("FORCE_GATEWAY_SAMPLE_EVERY", raising=False)
    assert resolve_sample_every() == 10
    monkeypatch.setenv("FORCE_GATEWAY_SAMPLE_EVERY", "0")
    assert resolve_sample_every() == 0
    monkeypatch.setenv("FORCE_GATEWAY_SAMPLE_EVERY", "3")
    assert resolve_sample_every() == 3
    monkeypatch.setenv("FORCE_GATEWAY_SAMPLE_EVERY", "junk")
    assert resolve_sample_every() == 10


def test_judge_off_is_zero_behavior_change():
    client = make_client(judge=None)
    call(client)
    t = client.get("/telemetry").json()
    assert t["coverage"]["instrumented"] == 1
    assert t["coverage"]["judged_samples"] == 0
    assert t["recent"][-1]["judgment"] is None
    assert t["active_alerts"] == []


# --- deterministic sampling + metering ---

def test_sampling_is_deterministic_1_in_n():
    judge = MockHygieneJudge(scores=[0.9])
    gov = FakeGovernor()
    client = make_client(judge=judge, sample_every=2, governor=gov)
    for _ in range(4):
        call(client)
    assert len(judge.calls) == 2  # calls 2 and 4 exactly
    t = client.get("/telemetry").json()
    assert t["coverage"]["judged_samples"] == 2
    judged = [r["judgment"] is not None for r in t["recent"]]
    assert judged == [False, True, False, True]


def test_judged_sample_meters_gateway_usage():
    judge = MockHygieneJudge(scores=[0.9])
    gov = FakeGovernor()
    client = make_client(judge=judge, sample_every=1, governor=gov)
    call(client)
    usage_posts = [j for p, j in gov.posts if p == "/usage"]
    assert any(j["agent_id"] == SELF_AGENT_ID
               and j["note"] == "gateway hygiene judgment"
               and j["input_tokens"] > 0 for j in usage_posts)


# --- fail-open judge paths: request always succeeds, gap always counted ---

@pytest.mark.parametrize("governor,reason", [
    (None, "no_governor"),
    (FakeGovernor(status_code=404), "no_cap"),
    (FakeGovernor(state="BLOCK"), "budget"),
    (FakeGovernor(raise_get=True), "governor_unreachable"),
    (FakeGovernor(status_code=500), "governor_error"),
])
def test_fail_open_spend_gate(governor, reason):
    judge = MockHygieneJudge(scores=[0.9])
    client = make_client(judge=judge, sample_every=1, governor=governor)
    call(client)  # never fails
    t = client.get("/telemetry").json()
    assert t["coverage"]["judge_bypassed"] == {reason: 1}
    assert t["coverage"]["judged_samples"] == 0
    assert judge.calls == []  # gate sits before the model
    assert t["recent"][-1]["hygiene"]  # structural telemetry still on


def test_fail_open_judge_error():
    judge = MockHygieneJudge(raise_error=RuntimeError("boom"))
    client = make_client(judge=judge, sample_every=1, governor=FakeGovernor())
    call(client)
    t = client.get("/telemetry").json()
    assert t["coverage"]["judge_bypassed"] == {"error": 1}
    assert t["coverage"]["instrumented"] == 1


# --- trend alerts: two consecutive windows, never a single point ---

def _run_scores(scores):
    """window_size=2, baseline_windows=2: scores land two per window."""
    judge = MockHygieneJudge(scores=scores)
    ledger = FakeLedger()
    client = make_client(judge=judge, sample_every=1, governor=FakeGovernor(),
                         ledger=ledger)
    for _ in range(len(scores)):
        call(client)
    return client, ledger


def test_drift_alert_fires_on_two_consecutive_bad_windows_only_once():
    # windows: [.9,.9] [.9,.9] baseline=0.9 | [.4,.4] out#1 | [.4,.4] out#2
    # -> ONE alert per (route, dimension) | [.4,.4] still active, no re-fire.
    # D2b: a numeric mock score feeds BOTH series (overall, sycophancy), so
    # the episode yields exactly one alert for each — never relaxed to >= 1.
    client, ledger = _run_scores([0.9] * 4 + [0.4] * 6)
    alerts = [e for e in ledger.events if e["event_type"] == "gateway.drift_alert"]
    for dimension in ("overall", "sycophancy"):
        mine = [a for a in alerts if a["payload"]["dimension"] == dimension]
        assert len(mine) == 1, dimension
        assert mine[0]["payload"]["route"] == "analysis"
        assert mine[0]["payload"]["baseline_mean"] == 0.9
    assert len(alerts) == 2  # == number of series fed
    t = client.get("/telemetry").json()
    assert t["active_alerts"] == [{"route": "analysis", "dimension": "overall"},
                                  {"route": "analysis", "dimension": "sycophancy"}]
    assert t["hygiene_trend"]["analysis"]["overall"]["alerts_fired"] == 1
    assert t["hygiene_trend"]["analysis"]["sycophancy"]["alerts_fired"] == 1


def test_single_bad_window_then_recovery_never_alerts():
    # [.9,.9] [.9,.9] baseline | [.4,.4] out#1 | [.9,.9] back in band -> re-arm
    client, ledger = _run_scores([0.9] * 4 + [0.4, 0.4] + [0.9, 0.9])
    alerts = [e for e in ledger.events if e["event_type"] == "gateway.drift_alert"]
    for dimension in ("overall", "sycophancy"):
        assert [a for a in alerts if a["payload"]["dimension"] == dimension] == []
    assert alerts == []
    t = client.get("/telemetry").json()
    assert t["active_alerts"] == []
    for dimension in ("overall", "sycophancy"):
        assert t["hygiene_trend"]["analysis"][dimension]["consecutive_out_of_band"] == 0


def test_judge_change_resets_baseline():
    tracker = DriftTracker(window_size=1, band=0.1, baseline_windows=1)
    assert tracker.record("r", "overall", 0.9, "model-a", "hygiene-v1") is None  # baseline
    # model swap: scores not comparable — no alert, fresh baseline forms
    assert tracker.record("r", "overall", 0.2, "model-b", "hygiene-v1") is None
    st = tracker.status()["r"]["overall"]
    assert st["model"] == "model-b" and st["baseline_mean"] == 0.2
    assert st["alerts_fired"] == 0


# --- fail-open full bypass: fault and latency, visible, re-arming ---

def test_instrumentation_fault_bypasses_without_failing_traffic(monkeypatch):
    seen_bodies = []

    def spying_upstream(body, headers):
        seen_bodies.append(body)
        return mock_upstream(body, headers)

    fault = {"remaining": 1}
    from force_gateway import api as api_mod
    real_analyze = api_mod.analyze

    def flaky_analyze(text):
        if fault["remaining"] > 0:
            fault["remaining"] -= 1
            raise RuntimeError("telemetry crashed")
        return real_analyze(text)

    monkeypatch.setattr(api_mod, "analyze", flaky_analyze)
    ledger = FakeLedger()
    client = make_client(upstream=spying_upstream, ledger=ledger,
                         bypass_cooldown=2)

    call(client)  # fault -> 200 anyway, bypass entered
    bypasses = [e for e in ledger.events if e["event_type"] == "gateway.bypass"]
    assert len(bypasses) == 1
    assert bypasses[0]["payload"]["reason"] == "instrumentation_fault"

    call(client)  # bypassed: forwarded UNINSTRUMENTED
    call(client)  # bypassed
    assert "system" not in seen_bodies[1] and "system" not in seen_bodies[2]

    call(client)  # cooldown over: re-armed, instrumented again
    assert str(seen_bodies[3].get("system", "")).startswith("# FORCE Runtime Protocol")

    t = client.get("/telemetry").json()
    cov = t["coverage"]
    assert cov["bypassed"] == 2
    assert cov["bypass_entries"] == 1
    assert cov["bypass_reasons"] == {"instrumentation_fault": 1}
    assert cov["instrumented"] == 2  # calls 1 and 4


def test_latency_budget_triggers_bypass():
    ledger = FakeLedger()
    client = make_client(ledger=ledger, latency_budget_ms=-1.0,
                         bypass_cooldown=3)
    call(client)  # overhead > -1 always -> bypass entered after serving
    t = client.get("/telemetry").json()
    assert t["coverage"]["bypass_reasons"] == {"latency_budget": 1}
    assert t["coverage"]["bypass_remaining"] == 3
    assert [e["payload"]["reason"] for e in ledger.events
            if e["event_type"] == "gateway.bypass"] == ["latency_budget"]


# --- self-manifest (S4 pattern) ---

def test_self_manifest_validates_and_names_the_cto():
    data = load_self_manifest()
    assert validate_manifest_data(data).ok
    assert data["agent"]["name"] == SELF_AGENT_ID == "force-gateway"
    assert "CTO" in data["identity"]["principal"]
    cap = data["enforcement"]["spend_cap"]
    assert cap["limit"] == 5 and cap["period"] == "daily"
    assert cap["on_breach"] == "halt"
    assert round(cap["limit"] * 100) == 500  # cents, governor set-cap flow


def test_self_manifest_scope_is_observer_verbs_only():
    scope = load_self_manifest()["delegation"]["scope"]
    assert scope
    for entry in scope:
        assert entry.split()[0] in OBSERVER_VERBS, entry


def test_health_reports_judge_and_bypass():
    client = make_client(judge=MockHygieneJudge(), governor=FakeGovernor())
    h = client.get("/health").json()
    assert h["judge"] == "mock" and h["bypass_remaining"] == 0
    assert h["sample_every"] == 1
    assert HYGIENE_JUDGE_MODEL_DEFAULT.startswith("claude-haiku")
