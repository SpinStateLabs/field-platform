"""S6-11: a lone surrogate (the JSON escape ``\\ud800``) in the free-form manifest dicts of a crossing is a 422 with no
ledger append attempted. pydantic already refuses one in the typed ``str`` fields (``Name``, ``contract_ref``,
``request_summary``, ``manifest_signature``, ...); it does not look inside a ``dict[str, Any]``, so a manifest holding
one answered 200 and tried a ledger append. The walk is iterative and bounded: a deeply nested manifest is a 422, never
a RecursionError (500)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, CrossingRequest, FederationContract
from test_federation_broker import COUNTERPARTY

H = {"content-type": "application/json"}
MARK = "MADE-UP-MARKER-0123456789"
LONE = '"' + MARK + '\\ud800"'              # the raw JSON text of a string holding a lone surrogate


class Ledger:
    def __init__(self):
        self.calls = []

    def append(self, *a, **k):
        self.calls.append((a, k))
        return {}


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    store, ledger = ContractStore(tmp_path / "c.sqlite3"), Ledger()
    client = TestClient(create_app(engine=BrokerEngine(store=store, ledger=ledger)), raise_server_exceptions=False)
    return client, store, ledger


def contract_json(**swap):
    f = {"contract_id": '"x"', "counterparty_org": '"O"', "allowed_scopes": '["s"]', "allowed_data_classes": '["d"]',
         "contract_ref": "null"}
    f.update(swap)
    return "{" + ",".join(f'"{k}":{v}' for k, v in f.items()) + "}"


def crossing_json(**swap):
    f = {"counterparty_org": f'"{COUNTERPARTY}"', "counterparty_agent_id": '"a"', "counterparty_manifest": "{}",
         "scope": '"s"', "data_class": '"d"'}
    f.update(swap)
    return "{" + ",".join(f'"{k}":{v}' for k, v in f.items()) + "}"


def nested(depth: int) -> str:
    """Raw JSON for a list nested ``depth`` deep, as a manifest value."""
    return "[" * depth + "]" * depth


def rows(store):
    with store._lock:
        return store._conn.execute("SELECT count(*) FROM contracts").fetchone()[0]


# ---- the residual gap: free-form manifest dicts ---------------------------------------------------------------------

@pytest.mark.parametrize("manifest", [
    '{"k": ' + LONE + "}",                         # a value
    "{" + LONE + ": 1}",                           # a key
    '{"k": [' + LONE + "]}",                       # inside a list
    '{"a": {"b": {"c": [{"d": ' + LONE + "}]}}}",  # deep inside nested dicts and lists
    '{"k": ["ok", ' + LONE + "]}",
], ids=["value", "key", "list", "deep", "list-second"])
def test_an_inbound_manifest_with_a_lone_surrogate_is_422_and_no_ledger_append(rig, manifest):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(counterparty_manifest=manifest), headers=H)
    assert r.status_code == 422, (r.status_code, r.text[:160])
    assert MARK not in r.text
    assert ledger.calls == []


def test_an_outbound_manifest_with_a_lone_surrogate_is_422_and_no_ledger_append(rig):
    c, _, ledger = rig
    raw = ('{"direction":"outbound","counterparty_org":"%s","agent_id":"me","manifest":{"k":%s},"scope":"s",'
           '"data_class":"d"}' % (COUNTERPARTY, LONE))
    r = c.post("/crossing", content=raw, headers=H)
    assert r.status_code == 422 and MARK not in r.text and ledger.calls == []


def test_a_422_names_the_field_and_never_the_text(rig):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(counterparty_manifest='{"k": ' + LONE + "}"), headers=H)
    assert r.status_code == 422 and "counterparty_manifest" in r.text and MARK not in r.text
    assert ledger.calls == []


# ---- iterative walk and bounds: deep is a 422, never a 500 ----------------------------------------------------------

@pytest.mark.parametrize("depth", [100, 500, 2000])
def test_a_deeply_nested_manifest_is_422_not_500(rig, depth):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(counterparty_manifest='{"k": ' + nested(depth) + "}"), headers=H)
    assert r.status_code == 422, (depth, r.status_code, r.text[:160])
    assert ledger.calls == []


def test_an_absurdly_deep_body_is_refused_by_the_json_parser_never_a_500(rig):
    """Past what the JSON parser itself accepts the answer is its own 4xx (400 today), before any model runs."""
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(counterparty_manifest='{"k": ' + nested(20000) + "}"), headers=H)
    assert 400 <= r.status_code < 500, r.status_code
    assert ledger.calls == []


def test_a_deeply_nested_outbound_manifest_is_422_not_500(rig):
    c, _, ledger = rig
    raw = ('{"direction":"outbound","counterparty_org":"%s","agent_id":"me","manifest":{"k":%s},"scope":"s",'
           '"data_class":"d"}' % (COUNTERPARTY, nested(2000)))
    assert c.post("/crossing", content=raw, headers=H).status_code == 422 and ledger.calls == []


def test_the_model_walk_survives_a_depth_that_would_exhaust_the_recursion_limit():
    deep: list = []
    for _ in range(50_000):
        deep = [deep]
    with pytest.raises(ValueError, match="nests deeper"):
        CrossingRequest(counterparty_org="O", counterparty_agent_id="a", counterparty_manifest={"k": deep},
                        scope="s", data_class="d")


def test_a_manifest_with_too_many_values_is_refused():
    big = {"k": [0] * 60_000}
    with pytest.raises(ValueError, match="more than"):
        CrossingRequest(counterparty_org="O", counterparty_agent_id="a", counterparty_manifest=big,
                        scope="s", data_class="d")


def test_the_model_refuses_a_lone_surrogate_in_a_manifest_without_http_too():
    with pytest.raises(ValueError, match="UTF-8") as e:
        CrossingRequest(counterparty_org="O", counterparty_agent_id="a", counterparty_manifest={"k": ["a\ud800"]},
                        scope="s", data_class="d")
    assert "ud800" not in str(e.value) and "\ud800" not in str(e.value)


# ---- what main already constrains still answers 422 -----------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("allowed_scopes", f"[{LONE}]"), ("allowed_scopes", f'["ok",{LONE}]'), ("allowed_data_classes", f"[{LONE}]"),
    ("contract_ref", LONE), ("counterparty_org", LONE), ("contract_id", LONE),
])
def test_a_contract_with_a_lone_surrogate_is_422_and_writes_nothing(rig, field, value):
    c, store, _ = rig
    r = c.put("/contracts/x", content=contract_json(**{field: value}), headers=H)
    assert r.status_code == 422, (field, r.status_code, r.text[:120])
    assert MARK not in r.text
    assert rows(store) == 0
    assert c.get("/contracts").status_code == 200


@pytest.mark.parametrize("field", ["scope", "data_class", "request_summary", "counterparty_agent_id",
                                   "counterparty_org", "manifest_signature"])
def test_a_typed_crossing_text_field_with_a_lone_surrogate_is_422_and_no_ledger_append(rig, field):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(**{field: LONE}), headers=H)
    assert r.status_code == 422, (field, r.status_code, r.text[:120])
    assert MARK not in r.text
    assert ledger.calls == []


# ---- clean input is unaffected ------------------------------------------------------------------------------------

def test_a_clean_contract_with_non_ascii_text_still_registers(rig):
    c, store, _ = rig
    r = c.put("/contracts/x", content=contract_json(
        allowed_scopes='["échanger l\\u00e9ger", "日本語", "emoji \\ud83d\\ude00"]', contract_ref='"gc/été"'), headers=H)
    assert r.status_code == 200, r.text
    assert rows(store) == 1


def test_a_clean_crossing_with_a_non_ascii_manifest_still_decides_and_ledgers_once(rig):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(
        counterparty_manifest='{"nom": "héllo 日本", "e": "\\ud83d\\ude00", "l": [[1, [2]]]}',
        request_summary='"héllo 日本"'), headers=H)
    assert r.status_code == 200 and r.json()["decision"] in ("BLOCK", "ALLOW")
    assert len(ledger.calls) == 1


def test_the_contract_model_still_refuses_a_lone_surrogate_in_a_list_entry():
    with pytest.raises(ValueError):
        FederationContract(contract_id="x", counterparty_org="O", allowed_scopes=["a\ud800"],
                           allowed_data_classes=["d"])
