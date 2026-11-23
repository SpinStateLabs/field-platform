"""Pins for the README operator-row claims that no test covered (review of
PR 1102, F2): 422 on an empty operator for bulk and FLEET HALT, the key-only
half pair, a duplicated operator header answering 400, and resolve needing the
``escalation`` scope under ENFORCE (real spend-governor). Secrets are generated
at runtime."""
from __future__ import annotations

import json
import secrets

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import ServiceClient, create_app

MODES = ("off", "log_only", "enforce")


class Rec:
    def __init__(self):
        self.calls = []

    def post(self, path, **kw):
        self.calls.append((path, kw))

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

        return R()

    def get(self, path, **kw):
        raise ConnectionError("n/a")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def console():
    ks, other = Rec(), Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    app = create_app(registry=sc(other), ledger=sc(other), delegation=sc(other),
                     governor=sc(other), killswitch=sc(ks), sentinel=sc(other))
    return TestClient(app), ks


def _set_mode(monkeypatch, mode):
    if mode in ("log_only", "enforce"):
        monkeypatch.setenv(oa.ENV_REGISTRY, "operators.json")
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def _key() -> str:
    return "fok_" + secrets.token_hex(12)


def test_bulk_empty_operator_is_422_and_not_proxied(console):
    c, ks = console
    assert c.post("/api/agents/bulk", json={"agent_ids": ["a1"], "action": "kill", "operator": ""}).status_code == 422
    assert ks.calls == []


def test_fleet_halt_empty_operator_is_422_and_not_proxied(console):
    c, ks = console
    body = {"operator": "", "reason": "r", "confirm": "HALT", "domains": ["d1"]}
    assert c.post("/api/fleet/halt", json=body).status_code == 422
    assert ks.calls == []


@pytest.mark.parametrize("mode,status", [("off", 200), ("log_only", 200), ("enforce", 401)])
def test_key_only_half_pair_is_dropped_in_off_and_log_only_and_401_in_enforce(console, monkeypatch, mode, status):
    c, ks = console
    _set_mode(monkeypatch, mode)
    r = c.post("/api/agents/a1/kill", json={"operator": "don"}, headers={oa.HEADER_KEY: _key()})
    assert r.status_code == status
    if status == 200:
        assert "headers" not in ks.calls[-1][1]
    else:
        assert ks.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("dup", [oa.HEADER_OPERATOR, oa.HEADER_KEY])
def test_duplicated_operator_header_is_400_in_every_mode_and_not_proxied(console, monkeypatch, mode, dup):
    c, ks = console
    _set_mode(monkeypatch, mode)
    pair = [(oa.HEADER_OPERATOR, "don"), (oa.HEADER_KEY, _key())]
    pair.append((dup, dict(pair)[dup]))
    assert c.post("/api/agents/a1/kill", json={"operator": "don"}, headers=pair).status_code == 400
    assert ks.calls == []


def test_real_governor_resolve_needs_the_escalation_scope_under_enforce(tmp_path, monkeypatch):
    from spend_governor.api import create_app as gov_app
    from spend_governor.core import GovernorStore

    keys = {"esc": _key(), "caps": _key()}
    reg = tmp_path / "operators.json"
    reg.write_text(json.dumps([
        {"operator_id": oid, "key_sha256": oa.key_sha256(k), "status": "active", "scopes": [oid if oid == "caps" else "escalation"]}
        for oid, k in keys.items()]))
    store = GovernorStore(tmp_path / "g.sqlite3")
    gc = TestClient(gov_app(store=store))
    ids = []
    for agent in ("a1", "a2"):
        assert gc.put(f"/caps/{agent}", json={"agent_id": agent, "limit_cents": 100, "period": "total",
                                              "escalate_at_pct": 80}).status_code == 200
        assert gc.post("/spend", json={"agent_id": agent, "cents": 90}).status_code == 201
        ids.append(gc.get("/escalations", params={"agent_id": agent}).json()[0]["escalation_id"])
    monkeypatch.setenv(oa.ENV_REGISTRY, str(reg))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    body = {"resolved_by": "typed"}

    def hdr(oid):
        return {oa.HEADER_OPERATOR: oid, oa.HEADER_KEY: keys[oid]}

    assert gc.post(f"/escalations/{ids[0]}/resolve", json=body, headers=hdr("caps")).status_code == 403
    r = gc.post(f"/escalations/{ids[0]}/resolve", json=body, headers=hdr("esc"))
    assert (r.status_code, r.json()["resolved_by"]) == (200, "esc")
    store.close()


def test_readme_says_enforce_is_per_process_and_the_console_checks_presence_only():
    from pathlib import Path
    row = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text().split())
    assert "When the delegation service itself runs ENFORCE" in row
    assert "the console checks presence, not validity" in row
    assert "when the governor itself runs ENFORCE resolve needs an operator with the `escalation` scope" in row
    assert "Under ENFORCE the delegation service then requires" not in row
    assert "and under ENFORCE resolve needs a scoped operator" not in row
