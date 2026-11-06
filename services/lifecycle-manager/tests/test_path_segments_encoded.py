"""S4-10: the engine put agent ids and token ids into request paths with plain f-strings. provision() takes the id from
manifest.agent.name, which the schema constrains only to minLength 1, so a name holding '/', '?', '#' or '..' addressed a
DIFFERENT route on the registry, governor or kill-switch client (which attach the operator pair by path). Every id is now
ONE encoded path segment (quote(safe='') and, for the dot segments '.' and '..' that quote leaves alone, %2E).
Recording fake clients; ordinary ids must produce byte-identical paths."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from lifecycle_manager.engine import LifecycleEngine, SweepConfig

NOW = datetime.now(timezone.utc).replace(microsecond=0)
HOSTILE = ["a/b", "a?x=1", "a#f", "../x", "a b", "..", ".", "a%2Fb", "x/../../kill/other", "é"]
MANIFEST = """\
schema_version: field.spinstatelabs.ca/v1
agent:
  name: {name}
  description: A synthetic test agent.
  version: "0.1.0"
federated:
  isolated: true
  allowed_peers: []
  contracts: []
identity:
  principal: Controller, Spin State Labs (test)
  org: Spin State Labs
  jurisdiction:
    - PIPEDA
  data_scope:
    may_access:
      - timesheet CSV (read)
    may_retain:
      - drafts
    may_transmit: []
  model_provider: Anthropic
enforcement:
  kill_switch:
    endpoint: http://127.0.0.1:8005/kill/x
    method: HTTP POST
  spend_cap:
    currency: USD
    limit: 500
    period: daily
    on_breach: halt
  irreversible_action_policy: require_human_approval
  escalation_triggers:
    - send invoice
ledger:
  cryptographic_seal: true
  seal_algorithm: sha-256-merkle
  retention_days: 2555
  logged_events:
    - every action
  store: sealed-ledger service
delegation:
  granted_by: Controller, Spin State Labs (test)
  scope:
    - read timesheets
  expiry: "2099-06-30"
  revocation:
    method: HTTP POST
    endpoint: http://127.0.0.1:8003/tokens/{{id}}/revoke
runtime_protocol:
  name: FORCE
  version: "1.0"
  preset: audit
"""


def resp(status=200, body=None):
    return SimpleNamespace(status_code=status, text=str(body), json=lambda: body)


class Rec:
    """A recording client: every call is (METHOD, path); `answers` maps (METHOD, path-prefix) to a response."""

    def __init__(self, answers=None):
        self.calls: list[tuple[str, str]] = []
        self.answers = answers or {}

    def _do(self, method, path, **kw):
        self.calls.append((method, path))
        for (m, prefix), r in self.answers.items():
            if m == method and path.startswith(prefix):
                return r
        return resp(404, {})

    def get(self, path, **kw):
        return self._do("GET", path, **kw)

    def post(self, path, **kw):
        return self._do("POST", path, **kw)

    def put(self, path, **kw):
        return self._do("PUT", path, **kw)

    def patch(self, path, **kw):
        return self._do("PATCH", path, **kw)


class Registry:
    def __init__(self, agents):
        self.agents, self.statuses = agents, []

    def get_agent(self, agent_id):
        return self.agents[agent_id]

    def set_status(self, agent_id, status):
        self.statuses.append((agent_id, status))

    def list_agents(self, **kw):
        return list(self.agents.values())


def seg(value):
    """The expected single-segment form: quoted, and the dot segments spelled out."""
    out = urllib.parse.quote(value, safe="")
    return {".": "%2E", "..": "%2E%2E"}.get(out, out)


def segments(path):
    return path.strip("/").split("/")


@pytest.mark.parametrize("agent_id", HOSTILE)
def test_provision_puts_the_id_in_one_encoded_segment_on_every_route(tmp_path, agent_id):
    manifest = tmp_path / "m.yaml"
    manifest.write_text(MANIFEST.format(name=repr(agent_id) if agent_id.strip() != agent_id else
                                        '"' + agent_id.replace('"', '\\"') + '"'), encoding="utf-8")
    reg = Rec({("POST", "/agents"): resp(409, {}),                           # already registered -> GET then PATCH
               ("GET", "/agents/"): resp(200, {"status": "active", "owner": "someone-else", "manifest_ref": "other"}),
               ("PATCH", "/agents/"): resp(200, {})})
    gov = Rec({("PUT", "/caps/"): resp(200, {}), ("GET", "/rate-limits"): resp(404, {})})
    dele = Rec({("POST", "/tokens"): resp(201, {"token_id": "t1", "expires_at": "2099-01-01T00:00:00+00:00"})})
    eng = LifecycleEngine(registry=Registry({}), delegation=dele, registry_http=reg, governor=gov)
    report = eng.provision(manifest, owner="Don", domain="finance", grantor="Controller, Spin State Labs (test)",
                           ttl_days=1, now=NOW)
    assert report.agent_id == agent_id and report.ok, [s.model_dump() for s in report.steps]
    assert ("GET", f"/agents/{seg(agent_id)}") in reg.calls
    assert ("PATCH", f"/agents/{seg(agent_id)}") in reg.calls
    assert ("PUT", f"/caps/{seg(agent_id)}") in gov.calls
    for method, path in [*reg.calls, *[c for c in gov.calls if c[1].startswith("/caps/")]]:
        if path.startswith(("/agents/", "/caps/")):
            assert len(segments(path)) == 2, (method, path)                  # the route, plus ONE id segment
            assert "?" not in path and "#" not in path and " " not in path and ".." not in segments(path)


@pytest.mark.parametrize("agent_id", HOSTILE)
def test_decommission_encodes_the_kill_and_every_revoke_path(agent_id):
    token_id = "t/../x?y#z"
    registry = Registry({agent_id: {"agent_id": agent_id, "status": "active"}})
    dele = Rec({("GET", "/tokens"): resp(200, [{"token_id": token_id, "revoked": False},
                                                {"token_id": "..", "revoked": False}]),
                ("POST", "/tokens/"): resp(200, {})})
    kill = Rec({("POST", "/kill/"): resp(200, {})})
    eng = LifecycleEngine(registry=registry, delegation=dele, killswitch=kill)
    report = eng.decommission(agent_id, by="Don", reason="test", now=NOW)
    assert report.killed and report.tokens_revoked == [token_id, ".."]
    assert kill.calls == [("POST", f"/kill/{seg(agent_id)}")]
    assert len(segments(kill.calls[0][1])) == 2
    revokes = [c for c in dele.calls if c[0] == "POST"]
    assert revokes == [("POST", f"/tokens/{seg(token_id)}/revoke"), ("POST", "/tokens/%2E%2E/revoke")]
    for _, path in revokes:
        assert len(segments(path)) == 3 and segments(path)[2] == "revoke"


@pytest.mark.parametrize("agent_id", HOSTILE)
def test_sweep_auto_kill_of_an_orphan_encodes_the_id(agent_id):
    registry = Registry({agent_id: {"agent_id": agent_id, "owner": "Nobody", "status": "active",
                                    "created_at": NOW.isoformat()}})
    dele = Rec({("GET", "/tokens"): resp(200, [])})
    kill = Rec({("POST", "/kill/"): resp(200, {})})
    eng = LifecycleEngine(registry=registry, delegation=dele, killswitch=kill)
    report = eng.sweep("owner\nAlice\n", SweepConfig(auto_kill_orphans=True), now=NOW)
    assert [o.agent_id for o in report.orphans] == [agent_id] and report.orphans[0].auto_killed
    assert kill.calls == [("POST", f"/kill/{seg(agent_id)}")]
    assert len(segments(kill.calls[0][1])) == 2


def test_ordinary_ids_produce_byte_identical_paths():
    registry = Registry({"invoicing-agent": {"agent_id": "invoicing-agent", "status": "active"}})
    dele = Rec({("GET", "/tokens"): resp(200, [{"token_id": "0b1c2d3e-4f50-6789-abcd-ef0123456789", "revoked": False}]),
                ("POST", "/tokens/"): resp(200, {})})
    kill = Rec({("POST", "/kill/"): resp(200, {})})
    LifecycleEngine(registry=registry, delegation=dele, killswitch=kill).decommission(
        "invoicing-agent", by="Don", reason="x", now=NOW)
    assert kill.calls == [("POST", "/kill/invoicing-agent")]
    assert ("POST", "/tokens/0b1c2d3e-4f50-6789-abcd-ef0123456789/revoke") in dele.calls


def test_the_expected_form_helper_is_what_the_card_asks_for():
    assert seg("a/b") == "a%2Fb" and seg("a?x=1") == "a%3Fx%3D1" and seg("a#f") == "a%23f"
    assert seg("../x") == "..%2Fx" and seg("a b") == "a%20b" and seg("..") == "%2E%2E" and seg(".") == "%2E"
