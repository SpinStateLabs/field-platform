"""D5 — SDK federation: ``FederationClient``, ``CrossingBlocked``, ``fieldagent cross``.

The SDK asks the federation-broker and returns its verdict on ALLOW; BLOCK
raises ``CrossingBlocked`` carrying the verdict; an unreachable broker raises
``CrossingBlocked`` with ``verdict=None`` (fail closed, no invented clause).
The broker and ledger run in-process; every org, agent and key here is
synthetic (keys are generated per test).
"""

import json

import pytest
import typer
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from federation_broker.api import create_app as create_broker_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_agent import federation as fed
from field_agent._transport import AuthedClient
from field_agent.errors import FieldAgentError
from field_agent.federation import (
    UNREACHABLE_REASON,
    CrossingBlocked,
    FederationClient,
)
from field_core.clients import LedgerClient
from field_core.signing import generate_keypair, sign_manifest
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

HOME = "Spin State Labs"
COUNTERPARTY = "Borealis Example Corp"
OUR_AGENT = "invoicing-agent"
THEIR_AGENT = "borealis-billing-agent"
SCOPE = "exchange invoice status"
DATA_CLASS = "invoice metadata"


def manifest_for(agent, org, peer_org, peer_agent):
    data = template_data("client-facing-agent")
    data["agent"]["name"] = agent
    data["identity"].update(principal=f"Controller, {org} (demo)", org=org,
                            jurisdiction=["PIPEDA"], model_provider="Anthropic")
    data["enforcement"]["kill_switch"].update(endpoint="https://org.example/kill",
                                              method="HTTP POST")
    data["ledger"]["store"] = "sealed-ledger (demo)"
    data["delegation"].update(granted_by=f"Controller, {org} (demo)", scope=[SCOPE])
    data["delegation"]["revocation"] = {"method": "HTTP POST",
                                        "endpoint": "https://org.example/revoke"}
    data["federated"] = {
        "isolated": False,
        "allowed_peers": [{"agent_id": peer_agent, "org": peer_org,
                           "trust_basis": "federation contract FED-2026-001 (demo)"}],
        "contracts": [{"peer": peer_agent, "contract_ref": "FED-2026-001", "scope": SCOPE}],
    }
    return data


def our_manifest():
    return manifest_for(OUR_AGENT, HOME, COUNTERPARTY, THEIR_AGENT)


def their_manifest():
    return manifest_for(THEIR_AGENT, COUNTERPARTY, HOME, OUR_AGENT)


class Spy:
    """httpx-compatible pass-through that records what the SDK sent."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("post", url, dict(kwargs.get("headers") or {}), kwargs.get("json")))
        return self.inner.post(url, **kwargs)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, dict(kwargs.get("headers") or {}), None))
        return self.inner.get(url, **kwargs)


class DownClient:
    def post(self, *a, **k):
        raise ConnectionError("synthetic outage")

    get = post


class Canned:
    """Answers every POST with a fixed status/body (no broker behind it)."""

    def __init__(self, status, body):
        self.status, self.body = status, body

    def post(self, url, **kwargs):
        import httpx

        content = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return httpx.Response(self.status, content=content,
                              request=httpx.Request("POST", url))


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", HOME)
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    broker = TestClient(create_broker_app(engine=BrokerEngine(
        store=ContractStore(tmp_path / "contracts.sqlite3"),
        ledger=LedgerClient(client=AuthedClient(ledger), base_url="http://t"),
    )))
    r = broker.put("/contracts/FED-2026-001", json={
        "contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
        "allowed_scopes": [SCOPE], "allowed_data_classes": [DATA_CLASS],
        "contract_ref": "gc-vault/FED-2026-001 (demo)", "active": True})
    assert r.status_code == 200, r.text

    class S:
        pass

    s = S()
    s.ledger, s.broker, s.tmp_path = ledger, broker, tmp_path
    s.spy = Spy(broker)
    s.client = FederationClient(client=s.spy, base_url="http://t")
    s.events = lambda t: ledger.get("/events", params={"event_type": t}).json()
    return s


def test_allow_returns_verdict_and_ledgers_federation_allow(stack):
    verdict = stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert verdict["decision"] == "ALLOW"
    assert verdict["context"]["direction"] == "outbound"
    assert verdict["agent_id"] == f"{HOME}/{OUR_AGENT}"
    allows = stack.events("federation.allow")
    assert len(allows) == 1 and allows[0]["payload"]["direction"] == "outbound"


def test_the_sdk_asks_and_never_relays(stack):
    """One request, to the broker's decision route — nothing is sent to the
    counterparty, and no request payload beyond the envelope is carried."""
    stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest(),
                       request_summary="status of INV-0001 (synthetic)")
    assert [(verb, url) for verb, url, _, _ in stack.spy.calls] == [("post", "http://t/crossing")]
    sent = stack.spy.calls[0][3]
    assert set(sent) == {"direction", "counterparty_org", "agent_id", "manifest",
                         "scope", "data_class", "request_summary"}


def test_block_raises_crossing_blocked_with_the_clause(stack):
    with pytest.raises(CrossingBlocked) as caught:
        stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, "customer PII", our_manifest())
    exc = caught.value
    assert isinstance(exc, FieldAgentError)
    assert exc.verdict is not None and exc.verdict["decision"] == "BLOCK"
    assert exc.clause_id == "F.peer"
    assert "customer PII" in str(exc)
    assert len(stack.events("federation.block")) == 1


def test_isolated_manifest_raises_with_f_isolated(stack):
    manifest = our_manifest()
    manifest["federated"] = {"isolated": True, "allowed_peers": [], "contracts": []}
    with pytest.raises(CrossingBlocked) as caught:
        stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, manifest)
    assert caught.value.clause_id == "F.isolated"


def test_broker_down_raises_fail_closed_with_no_clause():
    client = FederationClient(client=DownClient(), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    exc = caught.value
    assert exc.verdict is None
    assert exc.clause_id is None
    assert str(exc).startswith(UNREACHABLE_REASON)
    assert UNREACHABLE_REASON == "federation-broker unreachable — failing closed"


@pytest.mark.parametrize("status, body", [
    (500, {"detail": "synthetic server error"}),
    # a verdict-shaped ALLOW body on a non-200 is still no decision
    (500, {"decision": "ALLOW", "agent_id": "x", "action": SCOPE, "reasons": []}),
    (201, {"decision": "ALLOW", "agent_id": "x", "action": SCOPE, "reasons": []}),
    (401, {"detail": "missing or invalid x-field-auth header"}),
    (422, {"detail": [{"msg": "synthetic"}]}),
    (200, b"not json"),
    (200, {"no": "decision here"}),
])
def test_no_decision_obtained_raises_fail_closed(status, body):
    client = FederationClient(client=Canned(status, body), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert caught.value.verdict is None
    assert "failing closed" in str(caught.value)


@pytest.mark.parametrize("decision", ["BLOCK", "ESCALATE", "allow", ""])
def test_only_an_exact_allow_proceeds(decision):
    body = {"decision": decision, "agent_id": "x", "action": SCOPE,
            "clause_id": "F.peer", "reasons": ["synthetic"]}
    client = FederationClient(client=Canned(200, body), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert caught.value.verdict == body


def test_secret_estate_carries_x_field_auth(stack, monkeypatch):
    from field_core.authn import ENV_VAR, HEADER

    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    bare = stack.broker.post("/crossing", json={
        "direction": "outbound", "counterparty_org": COUNTERPARTY, "agent_id": OUR_AGENT,
        "manifest": our_manifest(), "scope": SCOPE, "data_class": DATA_CLASS})
    assert bare.status_code == 401

    verdict = stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert verdict["decision"] == "ALLOW"
    assert stack.spy.calls[-1][2].get(HEADER) == "s3cret-demo-only"


def test_base_url_comes_from_field_federation_url(monkeypatch):
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://fedbroker.synthetic:8010/")
    seen = []

    class Record(Canned):
        def post(self, url, **kwargs):
            seen.append(url)
            return super().post(url, **kwargs)

    body = {"decision": "ALLOW", "agent_id": "x", "action": SCOPE, "reasons": []}
    FederationClient(client=Record(200, body)).cross(
        OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert seen == ["http://fedbroker.synthetic:8010/crossing"]


def test_manifest_may_be_a_yaml_path(stack):
    path = stack.tmp_path / "ours.yaml"
    path.write_text(yaml.safe_dump(our_manifest(), sort_keys=False), encoding="utf-8")
    assert stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, path)["decision"] == "ALLOW"


def test_inbound_via_the_sdk_passes_the_signature_through(stack):
    private_pem, public_pem = generate_keypair()
    r = stack.broker.put("/contracts/FED-2026-001", json={
        "contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
        "allowed_scopes": [SCOPE], "allowed_data_classes": [DATA_CLASS],
        "counterparty_pubkey_pem": public_pem, "active": True})
    assert r.status_code == 200, r.text
    theirs = their_manifest()

    with pytest.raises(CrossingBlocked) as unsigned:
        stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, theirs,
                           direction="inbound", counterparty_agent_id=THEIR_AGENT)
    assert "requires a signed manifest" in str(unsigned.value)

    verdict = stack.client.cross(
        OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, theirs, direction="inbound",
        counterparty_agent_id=THEIR_AGENT,
        manifest_signature=sign_manifest(theirs, private_pem))
    assert verdict["decision"] == "ALLOW"
    assert verdict["context"]["direction"] == "inbound"
    # outbound on the same keyed contract needs no signature (documented asymmetry)
    assert stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS,
                              our_manifest())["decision"] == "ALLOW"


@pytest.mark.parametrize("kwargs, needle", [
    ({"direction": "sideways"}, "direction"),
    ({"manifest_signature": "U1lOVEhFVElD"}, "manifest_signature"),
    ({"direction": "inbound"}, "counterparty_agent_id"),
])
def test_caller_errors_raise_before_any_request(stack, kwargs, needle):
    with pytest.raises(ValueError, match=needle):
        stack.client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest(), **kwargs)
    assert stack.spy.calls == []


# --- fieldagent cross ---------------------------------------------------------

@pytest.fixture()
def cli(stack, monkeypatch):
    app = typer.Typer()

    @app.callback()
    def _root():  # keeps `cross` a named subcommand, as in field_agent.cli
        pass

    fed.register_cli(app)
    monkeypatch.setattr(fed, "_cli_client", lambda: stack.client)
    manifest = stack.tmp_path / "ours.yaml"
    manifest.write_text(yaml.safe_dump(our_manifest(), sort_keys=False), encoding="utf-8")
    runner = CliRunner()

    def run(*args):
        return runner.invoke(app, ["cross", OUR_AGENT, "--org", COUNTERPARTY,
                                   "--scope", SCOPE, "--manifest", str(manifest), *args])

    return run


def test_cli_cross_exit_0_on_allow(cli):
    result = cli("--data-class", DATA_CLASS)
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert json.loads(result.output)["decision"] == "ALLOW"


def test_cli_cross_exit_1_on_block_prints_the_verdict(cli):
    result = cli("--data-class", "customer PII")
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit)  # a clean exit, not a crash
    assert '"clause_id": "F.peer"' in result.output


def test_cli_cross_exit_1_when_broker_unreachable(cli, monkeypatch):
    monkeypatch.setattr(fed, "_cli_client",
                        lambda: FederationClient(client=DownClient(), base_url="http://t"))
    result = cli("--data-class", DATA_CLASS)
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit)
    assert UNREACHABLE_REASON in result.output
    assert '"decision"' not in result.output  # no verdict invented


def test_cli_cross_exit_1_on_caller_error_without_asking(cli, stack):
    result = cli("--data-class", DATA_CLASS, "--signature", "U1lOVEhFVElD")
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.output and "manifest_signature" in result.output
    assert stack.spy.calls == []

    missing = cli("--data-class", DATA_CLASS, "--manifest", str(stack.tmp_path / "nope.yaml"))
    assert missing.exit_code == 1, missing.output
    assert isinstance(missing.exception, SystemExit)
    assert stack.spy.calls == []


def test_cli_cross_usage_error_is_click_exit_2(cli):
    result = cli()  # --data-class missing
    assert result.exit_code == 2, result.output


# --- FieldAgent.cross (wired by the integrator from the D5 shared edits) ------
# These were skip-guarded until the wiring landed; they are unconditional now,
# so removing the wiring fails them instead of skipping them.

def test_field_agent_cross_delegates_to_the_broker(stack):
    from field_agent import FieldAgent

    agent = FieldAgent(OUR_AGENT, sentinel_client=DownClient(), governor_client=DownClient(),
                       killswitch_client=DownClient(), federation_client=stack.spy,
                       federation_url="http://t")
    verdict = agent.cross(COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert verdict["agent_id"] == f"{HOME}/{OUR_AGENT}"
    with pytest.raises(CrossingBlocked) as caught:
        agent.cross(COUNTERPARTY, SCOPE, "customer PII", our_manifest())
    assert caught.value.clause_id == "F.peer"

    import field_agent

    assert field_agent.CrossingBlocked is CrossingBlocked
    assert field_agent.FederationClient is FederationClient


def test_field_agent_cross_keeps_the_opt_in_liveness_gate(stack):
    """With heartbeat_max_age set, cross() checks liveness first, like check():
    a kill-switch outage halts before the broker is even asked."""
    from field_agent import AgentKilled, FieldAgent

    agent = FieldAgent(OUR_AGENT, sentinel_client=DownClient(), governor_client=DownClient(),
                       killswitch_client=DownClient(), federation_client=stack.spy,
                       federation_url="http://t", heartbeat_max_age=30.0)
    with pytest.raises(AgentKilled):
        agent.cross(COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert stack.spy.calls == []


def test_fieldagent_cli_cross_is_registered(stack, monkeypatch):
    from field_agent import cli

    assert any(c.name == "cross" for c in cli.app.registered_commands)

    monkeypatch.setattr(fed, "_cli_client", lambda: stack.client)
    manifest = stack.tmp_path / "ours.yaml"
    manifest.write_text(yaml.safe_dump(our_manifest(), sort_keys=False), encoding="utf-8")
    base = ["cross", OUR_AGENT, "--org", COUNTERPARTY, "--scope", SCOPE,
            "--manifest", str(manifest)]
    runner = CliRunner()
    assert runner.invoke(cli.app, base + ["--data-class", DATA_CLASS]).exit_code == 0
    assert runner.invoke(cli.app, base + ["--data-class", "customer PII"]).exit_code == 1
