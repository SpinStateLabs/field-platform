"""v1.2 D2d/D2e — upstream selection, the keyless 502, and the passthrough
recursion guard."""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from force_gateway import api as api_mod
from force_gateway.api import (
    create_app,
    mock_upstream,
    passthrough_honoured,
    real_upstream,
)
from force_gateway.hygiene_judge import RUBRIC, AnthropicHygieneJudge, MockHygieneJudge

from test_gateway_delta import FakeGovernor, FakeLedger

SECRET = "synthetic-shared-secret-for-tests"
SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"
MSG = {"model": "m", "max_tokens": 16, "system": "caller system prompt",
       "messages": [{"role": "user", "content": "ping"}]}


class Spy:
    def __init__(self, respond=mock_upstream):
        self.bodies = []
        self.respond = respond

    def __call__(self, body, headers):
        self.bodies.append(json.loads(json.dumps(body)))
        return self.respond(body, headers)


# --- D2d: which upstream serves ---------------------------------------------

def test_keyless_real_upstream_answers_502_naming_the_key():
    client = TestClient(create_app())
    assert client.get("/health").json()["mock"] is False
    r = client.post("/v1/messages", json=MSG)
    assert r.status_code == 502
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert client.get("/telemetry").json()["total_requests"] == 0


def test_mock_env_exactly_1_serves_the_mock(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_MOCK", "1")
    client = TestClient(create_app())
    assert client.get("/health").json()["mock"] is True
    r = client.post("/v1/messages", json=MSG)
    assert r.status_code == 200
    assert r.json()["model"].startswith("force-gateway-mock")


@pytest.mark.parametrize("value", ["true", "True", "yes", " 1", "1 ", "0", ""])
def test_mock_env_near_misses_do_not_mock(monkeypatch, value):
    monkeypatch.setenv("FORCE_GATEWAY_MOCK", value)
    client = TestClient(create_app())
    assert client.get("/health").json()["mock"] is False
    assert client.post("/v1/messages", json=MSG).status_code == 502


def test_injected_upstream_outranks_the_mock_env(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_MOCK", "1")
    spy = Spy()
    app = create_app(upstream=spy)
    assert app.state.upstream is spy
    assert TestClient(app).post("/v1/messages", json=MSG).status_code == 200
    assert len(spy.bodies) == 1


@pytest.mark.parametrize("args,mock", [(["serve", "--mock"], True), (["serve"], False)])
def test_cli_mock_flag_is_kept(monkeypatch, args, mock):
    import uvicorn

    from force_gateway.cli import app as cli_app

    monkeypatch.setenv("FORCE_GATEWAY_MOCK", "")  # restored after the test
    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(app=app))
    result = CliRunner().invoke(cli_app, args)
    assert result.exit_code == 0, result.output
    assert (served["app"].state.upstream is mock_upstream) is mock


def test_fourth_reader_real_upstream_ignores_force_gateway_url(monkeypatch):
    import httpx

    calls = []

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, headers))
        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    assert real_upstream(MSG, {}) == (200, {"ok": True})
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000/")
    real_upstream(MSG, {})
    assert [url for url, _ in calls] == ["https://api.anthropic.com/v1/messages",
                                         "http://proxy.example.test:9000/v1/messages"]
    for _, headers in calls:
        assert "x-field-auth" not in headers and "x-force-passthrough" not in headers


# --- D2e: passthrough -------------------------------------------------------

def test_passthrough_honoured_rules(monkeypatch):
    assert passthrough_honoured("judge", None) is True
    assert passthrough_honoured(None, None) is False
    assert passthrough_honoured("JUDGE", None) is False
    assert passthrough_honoured("yes", None) is False
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    assert passthrough_honoured("judge", None) is False
    assert passthrough_honoured("judge", "wrong") is False
    assert passthrough_honoured("judge", SECRET) is True


def _passthrough_app(**kw):
    spy = Spy()
    ledger = FakeLedger()
    gov = FakeGovernor()
    judge = MockHygieneJudge(scores=[0.9])
    app = create_app(upstream=spy, governor_client=gov, ledger_client=ledger,
                     hygiene_judge=judge, sample_every=1,
                     latency_budget_ms=10_000.0, **kw)
    return app, spy, ledger, gov, judge


def test_secretless_passthrough_is_forwarded_untouched_counted_and_ledgered():
    # A platform judge's call exactly as field_core.llm builds it: no agent id.
    app, spy, ledger, gov, judge = _passthrough_app()
    client = TestClient(app)
    r = client.post("/v1/messages", json=MSG, headers={"x-force-passthrough": "judge"})
    assert r.status_code == 200
    assert spy.bodies == [MSG]  # no FORCE block, caller system untouched
    t = client.get("/telemetry").json()
    assert t["total_requests"] == 0 and t["by_preset"] == {} and t["recent"] == []
    assert t["coverage"]["passthrough"] == 1
    assert t["coverage"]["instrumented"] == 0
    assert judge.calls == []  # never sampled
    assert gov.posts == []    # no agent id: nothing to attribute (the judge meters its own cap)
    assert [(e["event_type"], e["payload"]) for e in ledger.events] == [
        ("gateway.passthrough", {"client_host": "testclient", "agent_id": None})]


PASSTHROUGH_USAGE = ("/usage", {"agent_id": "rogue-agent",
                                "model": "force-gateway-mock (no upstream call made)",
                                "input_tokens": 240, "output_tokens": 118,
                                "note": "force-gateway LLM call (passthrough)"})


@pytest.mark.parametrize("secret", [None, SECRET])
def test_passthrough_cannot_switch_off_an_agents_token_metering(monkeypatch, secret):
    """`x-force-passthrough` exempts a call from injection, telemetry and
    sampling — never from metering: a call naming an agent is reported to the
    governor exactly once, on a secret estate too (where every agent holds the
    secret and no passthrough is ledgered)."""
    if secret:
        monkeypatch.setenv("FIELD_SHARED_SECRET", secret)
    app, spy, ledger, gov, judge = _passthrough_app()
    client = TestClient(app, headers={"x-field-auth": secret} if secret else None)
    r = client.post("/v1/messages", json=MSG,
                    headers={"x-force-passthrough": "judge",
                             "x-field-agent-id": "rogue-agent"})
    assert r.status_code == 200 and spy.bodies == [MSG]
    assert gov.posts == [PASSTHROUGH_USAGE]
    assert judge.calls == []
    t = client.get("/telemetry").json()
    assert t["coverage"]["passthrough"] == 1 and t["total_requests"] == 0
    expected_ledger = [] if secret else [
        ("gateway.passthrough", {"client_host": "testclient", "agent_id": "rogue-agent"})]
    assert [(e["event_type"], e["payload"]) for e in ledger.events] == expected_ledger


def test_passthrough_metering_falls_back_to_spend_and_never_fails_the_call(tmp_path):
    from force_gateway.store import GatewayStore

    class Resp:
        def __init__(self, code):
            self.status_code = code

    class OldGovernor(FakeGovernor):
        def post(self, path, json=None):
            self.posts.append((path, json))
            return Resp(404 if path == "/usage" else 201)

    class DownGovernor(FakeGovernor):
        def post(self, path, json=None):
            raise ConnectionError("governor down (synthetic)")

    headers = {"x-force-passthrough": "judge", "x-field-agent-id": "rogue-agent"}
    old = OldGovernor()
    app = create_app(upstream=mock_upstream, governor_client=old, sample_every=0)
    assert TestClient(app).post("/v1/messages", json=MSG, headers=headers).status_code == 200
    assert old.posts == [PASSTHROUGH_USAGE, ("/spend", {
        "agent_id": "rogue-agent", "tokens": 358,
        "note": "force-gateway LLM call (passthrough)"})]

    app = create_app(upstream=mock_upstream, governor_client=DownGovernor(), sample_every=0,
                     store=GatewayStore(tmp_path / "down.sqlite3"))
    client = TestClient(app)
    assert client.post("/v1/messages", json=MSG, headers=headers).status_code == 200
    assert app.state.coverage["passthrough"] == 1


def test_a_failed_passthrough_upstream_is_not_metered():
    app, spy, ledger, gov, judge = _passthrough_app()
    spy.respond = lambda body, headers: (529, {"error": "overloaded"})
    r = TestClient(app).post("/v1/messages", json=MSG,
                             headers={"x-force-passthrough": "judge",
                                      "x-field-agent-id": "rogue-agent"})
    assert r.status_code == 529 and gov.posts == []


def test_passthrough_does_not_consume_a_bypass_window():
    app, spy, *_ = _passthrough_app()
    app.state.bypass_remaining = 2
    client = TestClient(app)
    client.post("/v1/messages", json=MSG, headers={"x-force-passthrough": "judge"})
    assert app.state.bypass_remaining == 2
    assert app.state.coverage["bypassed"] == 0


def test_passthrough_upstream_error_is_passed_on():
    app, spy, *_ = _passthrough_app()
    spy.respond = lambda body, headers: (529, {"error": "overloaded"})
    r = TestClient(app).post("/v1/messages", json=MSG,
                             headers={"x-force-passthrough": "judge"})
    assert r.status_code == 529
    assert app.state.coverage["passthrough"] == 1


def test_unrecognised_passthrough_value_is_instrumented():
    app, spy, ledger, *_ = _passthrough_app()
    client = TestClient(app)
    client.post("/v1/messages", json=MSG, headers={"x-force-passthrough": "yes"})
    assert spy.bodies[0]["system"].startswith("# FORCE Runtime Protocol")
    t = client.get("/telemetry").json()
    assert t["by_preset"] == {"analysis": 1} and t["coverage"]["passthrough"] == 0
    assert "gateway.passthrough" not in [e["event_type"] for e in ledger.events]


def test_secret_estate_authenticated_passthrough_is_honoured_not_ledgered(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    app, spy, ledger, *_ = _passthrough_app()
    client = TestClient(app, headers={"x-field-auth": SECRET})
    r = client.post("/v1/messages", json=MSG, headers={"x-force-passthrough": "judge"})
    assert r.status_code == 200 and spy.bodies == [MSG]
    t = client.get("/telemetry").json()
    assert t["coverage"]["passthrough"] == 1 and t["total_requests"] == 0
    assert ledger.events == []


def test_secret_estate_unauthenticated_passthrough_never_reaches_upstream(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    app, spy, *_ = _passthrough_app()
    r = TestClient(app).post("/v1/messages", json=MSG,
                             headers={"x-force-passthrough": "judge"})
    assert r.status_code == 401  # the perimeter middleware answers first
    assert spy.bodies == [] and app.state.coverage["passthrough"] == 0


@pytest.mark.parametrize("presented", [None, "wrong-secret"])
def test_handler_gate_ignores_unauthenticated_passthrough_under_a_secret(monkeypatch, presented):
    """Defence in depth: were /v1/messages ever opened past the perimeter
    middleware (e.g. to agents holding tokens, not the secret), a passthrough
    without the secret is IGNORED — instrumented and counted — not honoured."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    app, spy, ledger, *_ = _passthrough_app()
    app.user_middleware.clear()  # simulate the route opened past authn
    client = TestClient(app)
    headers = {"x-force-passthrough": "judge"}
    if presented:
        headers["x-field-auth"] = presented
    assert client.post("/v1/messages", json=MSG, headers=headers).status_code == 200
    assert spy.bodies[0]["system"].startswith("# FORCE Runtime Protocol")
    t = client.get("/telemetry").json()
    assert t["by_preset"] == {"analysis": 1}
    assert t["coverage"]["passthrough"] == 0 and t["coverage"]["instrumented"] == 1


# --- the recursion guard, end to end ----------------------------------------

JUDGMENT = {"sycophancy": 0.25, "premise_rigor": 0.5, "overall": 0.75,
            "rationale": "synthetic judgment"}


def routing_upstream(calls):
    """Answers the hygiene rubric with a judgment, everything else with the mock."""
    def upstream(body, headers):
        calls.append(json.loads(json.dumps(body)))
        if body.get("system") == RUBRIC:
            return 200, {"model": "synthetic-judge", "type": "message",
                         "content": [{"type": "text", "text": json.dumps(JUDGMENT)}],
                         "usage": {"input_tokens": 3, "output_tokens": 2}}
        return mock_upstream(body, headers)
    return upstream


def route_httpx_clients_to(monkeypatch, app):
    """Every httpx.Client a caller builds talks to the in-process `app`,
    keeping the base_url and headers the CALLER chose."""
    import httpx

    built = []

    def client_factory(base_url="", timeout=None, headers=None, **kw):
        c = TestClient(app, base_url=str(base_url), headers=headers)
        built.append((str(base_url), dict(headers or {})))
        return c

    monkeypatch.setattr(httpx, "Client", client_factory)
    return built


def test_nested_judge_goes_through_the_gateway_and_cannot_resample(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    calls = []
    gov = FakeGovernor()
    app = create_app(upstream=routing_upstream(calls), governor_client=gov,
                     ledger_client=FakeLedger(), hygiene_judge=MockHygieneJudge(),
                     sample_every=1, latency_budget_ms=10_000.0)
    built = route_httpx_clients_to(monkeypatch, app)
    app.state.hygiene_judge = AnthropicHygieneJudge()  # the real client class
    assert built[0][0] == "http://forcegw:8009"
    assert built[0][1]["x-field-auth"] == SECRET
    assert built[0][1]["x-force-passthrough"] == "judge"

    client = TestClient(app, headers={"x-field-auth": SECRET})
    assert client.post("/v1/messages", json=MSG).status_code == 200

    assert len(calls) == 2  # the agent's call, then the judge's nested call
    assert calls[0]["system"].startswith("# FORCE Runtime Protocol")
    assert calls[1]["system"] == RUBRIC  # forwarded untouched: not re-injected
    t = client.get("/telemetry").json()
    assert t["total_requests"] == 1 and t["by_preset"] == {"analysis": 1}
    assert t["coverage"]["passthrough"] == 1
    assert t["coverage"]["judged_samples"] == 1
    assert t["coverage"]["judge_bypassed"] == {}  # the nested call got 200, not 401
    assert app.state.request_count == 1  # the nested call did not advance the stride
    judgment = t["recent"][0]["judgment"]
    assert (judgment["overall"], judgment["sycophancy"]) == (0.75, 0.25)
    assert t["hygiene_trend"]["analysis"]["sycophancy"]["scores_in_current_window"] == 1
    # The judge's spend is metered ONCE, on the gateway's own cap: its nested
    # passthrough call names no agent, so it is not metered a second time.
    assert [(path, p["agent_id"], p["input_tokens"]) for path, p in gov.posts] == [
        ("/usage", "force-gateway", 3)]


def test_without_the_gateway_url_a_secret_estate_judge_gets_401_not_the_secret(monkeypatch):
    """Negative control for the test above: pointed at ANTHROPIC_BASE_URL the
    judge carries no x-field-auth (never sent to a possible third party), so a
    secret-protected gateway refuses it and the gap is counted."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://forcegw:8009")
    calls = []
    app = create_app(upstream=routing_upstream(calls), governor_client=FakeGovernor(),
                     hygiene_judge=MockHygieneJudge(), sample_every=1,
                     latency_budget_ms=10_000.0)
    built = route_httpx_clients_to(monkeypatch, app)
    app.state.hygiene_judge = AnthropicHygieneJudge()
    assert "x-field-auth" not in built[0][1]
    client = TestClient(app, headers={"x-field-auth": SECRET})
    assert client.post("/v1/messages", json=MSG).status_code == 200
    assert len(calls) == 1
    assert client.get("/telemetry").json()["coverage"]["judge_bypassed"] == {"error": 1}


def test_streaming_limits_line_is_kept_verbatim():
    from pathlib import Path

    readme = (Path(api_mod.__file__).resolve().parents[2] / "README.md").read_text(
        encoding="utf-8").replace("\r\n", "\n")
    assert ("- v0.1 speaks the Anthropic Messages shape only; no streaming (`stream:\n"
            "  true` is not intercepted — telemetry would miss those responses), no\n"
            "  OpenAI translation layer.") in readme


def test_demo_uses_the_mock_env_var_not_the_flag():
    from pathlib import Path

    demo = (Path(api_mod.__file__).resolve().parents[2] / "demo.sh").read_text(encoding="utf-8")
    assert "FORCE_GATEWAY_MOCK=1 forcegw serve" in demo
    assert "--mock" not in demo
