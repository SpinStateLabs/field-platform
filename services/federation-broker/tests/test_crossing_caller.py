"""POST /crossing: asked by an operator with the crossing scope, or by the named agent with its own active token."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from federation_broker.own_token import TOKEN_MAX, OwnTokenCheck
from field_core import operator_auth as oa

KEY_ALL = "fok_all-key-0123456789abcdef"
KEY_CROSS = "fok_cross-key-0123456789abcdef"
KEY_KILL = "fok_kill-key-0123456789abcdef"
AGENT = "example-agent"
OUT = {"direction": "outbound", "counterparty_org": "Borealis Example", "agent_id": AGENT, "manifest": {},
       "scope": "read", "data_class": "public"}
IN = {"direction": "inbound", "counterparty_org": "Borealis Example", "counterparty_agent_id": AGENT,
      "counterparty_manifest": {}, "scope": "read", "data_class": "public"}


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload=None, agent_id=None, **_):
        self.rows.append((event_type, payload, agent_id))


class Reply:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Authority:
    """Stands in for delegation-authority's POST /introspect: ``tokens`` maps a token id to the reply."""

    def __init__(self, tokens):
        self.tokens, self.asked = tokens, []

    def post(self, url, json=None, headers=None):
        self.asked.append((url, json["token_id"]))
        reply = self.tokens.get(json["token_id"], Reply(200, {"active": False, "agent_id": None}))
        if isinstance(reply, ConnectionError):
            raise reply
        return reply


TOKENS = {
    "mine": Reply(200, {"active": True, "agent_id": AGENT}),
    "theirs": Reply(200, {"active": True, "agent_id": "another-agent"}),
    "revoked": Reply(200, {"active": False, "agent_id": AGENT}),
    "wordy": Reply(200, {"active": "true", "agent_id": AGENT}),
    "refused": Reply(500, {"active": True, "agent_id": AGENT}),
    "garbled": Reply(200, ValueError("not json")),
    "listed": Reply(200, [True]),
    "down": ConnectionError("no route"),
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))


def roster(tmp_path, monkeypatch, require=True):
    rows = [{"operator_id": name, "key_sha256": oa.key_sha256(key), "status": "active", "scopes": scopes}
            for name, key, scopes in (("all", KEY_ALL, ["*"]), ("cross", KEY_CROSS, ["crossing"]),
                                      ("kill", KEY_KILL, ["kill", "federation"]))]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if require:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


class NoRecord:
    def read(self, agent_id):
        return None, "no record in this test"


def broker(tmp_path):
    ledger, authority = Ledger(), Authority(TOKENS)
    app = create_app(BrokerEngine(store=ContractStore(tmp_path / "contracts.sqlite3"), ledger=ledger))
    app.state.own_token = OwnTokenCheck(client=authority, base_url="http://delegation.test")
    app.state.registered = NoRecord()          # these tests are about who may ask; the manifest has its own file
    return TestClient(app), ledger, authority


def verdicts(ledger):
    return [r for r in ledger.rows if r[0] in ("federation.allow", "federation.block")]


def operator(name, key):
    return {oa.HEADER_OPERATOR: name, oa.HEADER_KEY: key}


@pytest.mark.parametrize("body", [OUT, IN])
def test_without_a_caller_identity_nothing_is_decided(tmp_path, monkeypatch, body):
    roster(tmp_path, monkeypatch)
    client, ledger, _ = broker(tmp_path)
    assert client.post("/crossing", json=body).status_code == 401
    assert client.post("/crossing", json=body, headers=operator("all", "fok_wrong")).status_code == 403
    assert client.post("/crossing", json=body, headers=operator("kill", KEY_KILL)).status_code == 403
    assert verdicts(ledger) == []


@pytest.mark.parametrize("body", [OUT, IN])
@pytest.mark.parametrize("name,key", [("cross", KEY_CROSS), ("all", KEY_ALL)])
def test_an_operator_with_the_scope_may_ask_either_way(tmp_path, monkeypatch, body, name, key):
    roster(tmp_path, monkeypatch)
    client, ledger, authority = broker(tmp_path)
    r = client.post("/crossing", json=body, headers=operator(name, key))
    assert r.status_code == 200 and r.json()["decision"] == "BLOCK"      # an empty manifest: decided, and refused
    assert len(verdicts(ledger)) == 1 and authority.asked == []


def test_the_agent_may_ask_with_its_own_token(tmp_path, monkeypatch):
    roster(tmp_path, monkeypatch)
    client, ledger, authority = broker(tmp_path)
    r = client.post("/crossing", json=OUT, headers={"x-field-token": "mine"})
    assert r.status_code == 200, r.text
    assert authority.asked == [("http://delegation.test/introspect", "mine")]
    assert len(verdicts(ledger)) == 1
    assert "mine" not in json.dumps(ledger.rows, default=str)


@pytest.mark.parametrize("token", ["theirs", "revoked", "unknown", "wordy", "refused", "garbled", "listed", "down"])
def test_any_other_answer_about_the_token_is_a_no(tmp_path, monkeypatch, token):
    roster(tmp_path, monkeypatch)
    client, ledger, authority = broker(tmp_path)
    assert client.post("/crossing", json=OUT, headers={"x-field-token": token}).status_code == 401
    assert len(authority.asked) == 1 and verdicts(ledger) == []


def test_a_token_does_not_open_an_inbound_crossing_or_one_without_a_direction(tmp_path, monkeypatch):
    roster(tmp_path, monkeypatch)
    client, ledger, authority = broker(tmp_path)
    headers = {"x-field-token": "mine"}
    assert client.post("/crossing", json=IN, headers=headers).status_code == 401
    assert client.post("/crossing", json={**IN, "agent_id": AGENT}, headers=headers).status_code == 401
    assert client.post("/crossing", json={k: v for k, v in OUT.items() if k != "direction"}, headers=headers).status_code == 401
    assert client.post("/crossing", content=b"not json", headers=headers).status_code in (401, 422)
    assert authority.asked == [] and verdicts(ledger) == []


def test_an_over_long_token_is_not_asked_about(tmp_path, monkeypatch):
    roster(tmp_path, monkeypatch)
    client, _, authority = broker(tmp_path)
    assert client.post("/crossing", json=OUT, headers={"x-field-token": "t" * (TOKEN_MAX + 1)}).status_code == 401
    assert authority.asked == []


def test_a_repeated_key_is_still_refused(tmp_path, monkeypatch):
    roster(tmp_path, monkeypatch)
    client, ledger, _ = broker(tmp_path)
    raw = json.dumps(OUT)[:-1] + ', "agent_id": "another-agent"}'
    r = client.post("/crossing", content=raw, headers={"x-field-token": "mine", "content-type": "application/json"})
    assert r.status_code == 422 and verdicts(ledger) == []


def test_log_only_decides_and_records_the_unidentified_caller_only(tmp_path, monkeypatch):
    roster(tmp_path, monkeypatch, require=False)
    client, ledger, _ = broker(tmp_path)
    assert client.post("/crossing", json=OUT, headers={"x-field-token": "mine"}).status_code == 200
    assert [r[0] for r in ledger.rows if r[0].startswith("operator.")] == []
    assert client.post("/crossing", json=OUT).status_code == 200
    assert [r[0] for r in ledger.rows if r[0].startswith("operator.")] == ["operator.unauthenticated"]


def test_with_the_operator_layer_off_nothing_changes(tmp_path):
    client, ledger, authority = broker(tmp_path)
    assert client.post("/crossing", json=OUT).status_code == 200
    assert client.post("/crossing", json=OUT, headers={"x-field-token": "theirs"}).status_code == 200
    assert authority.asked == [] and len(verdicts(ledger)) == 2
