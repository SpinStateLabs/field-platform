"""S6-11: a lone surrogate (the JSON escape ``\\ud800``) in a contract or crossing text field is a 422 with nothing written
and no ledger append attempted. pydantic already refused one in a plain ``str`` field; it let one through a list entry and
an optional string, so ``allowed_scopes`` / ``allowed_data_classes`` wrote the row and then 500'd serialising the answer,
and ``contract_ref`` 500'd at the SQLite bind."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, CrossingRequest, FederationContract
from test_federation_broker import COUNTERPARTY, counterparty_manifest

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


def rows(store):
    with store._lock:
        return store._conn.execute("SELECT count(*) FROM contracts").fetchone()[0]


@pytest.mark.parametrize("field,value", [
    ("allowed_scopes", f"[{LONE}]"), ("allowed_scopes", f'["ok",{LONE}]'), ("allowed_data_classes", f"[{LONE}]"),
    ("contract_ref", LONE), ("counterparty_org", LONE), ("contract_id", LONE),
], ids=lambda v: v if isinstance(v, str) and v.isidentifier() else "v")
def test_a_contract_with_a_lone_surrogate_is_422_and_writes_nothing(rig, field, value):
    c, store, _ = rig
    r = c.put("/contracts/x", content=contract_json(**{field: value}), headers=H)
    assert r.status_code == 422, (field, r.status_code, r.text[:120])
    assert MARK not in r.text
    assert rows(store) == 0
    assert c.get("/contracts").status_code == 200


def test_a_clean_contract_with_non_ascii_text_still_registers(rig):
    c, store, _ = rig
    r = c.put("/contracts/x", content=contract_json(allowed_scopes='["échanger l\\u00e9ger", "日本語", "emoji \\ud83d\\ude00"]',
                                                   contract_ref='"gc/été"'), headers=H)
    assert r.status_code == 200, r.text
    assert rows(store) == 1


def crossing_json(**swap):
    f = {"counterparty_org": f'"{COUNTERPARTY}"', "counterparty_agent_id": '"a"', "counterparty_manifest": "{}",
         "scope": '"s"', "data_class": '"d"'}
    f.update(swap)
    return "{" + ",".join(f'"{k}":{v}' for k, v in f.items()) + "}"


@pytest.mark.parametrize("field,value", [
    ("scope", LONE), ("data_class", LONE), ("request_summary", LONE), ("counterparty_agent_id", LONE),
    ("counterparty_org", LONE), ("manifest_signature", LONE), ("counterparty_manifest", '{"k": ' + LONE + "}"),
    ("counterparty_manifest", '{' + LONE + ': 1}'), ("counterparty_manifest", '{"k": [' + LONE + "]}"),
])
def test_a_crossing_with_a_lone_surrogate_is_422_and_no_ledger_append(rig, field, value):
    c, store, ledger = rig
    r = c.post("/crossing", content=crossing_json(**{field: value}), headers=H)
    assert r.status_code == 422, (field, r.status_code, r.text[:120])
    assert MARK not in r.text
    assert ledger.calls == []


def test_an_outbound_crossing_field_too(rig):
    c, _, ledger = rig
    raw = ('{"direction":"outbound","counterparty_org":"%s","agent_id":"me","manifest":{"k":%s},"scope":"s",'
           '"data_class":"d"}' % (COUNTERPARTY, LONE))
    assert c.post("/crossing", content=raw, headers=H).status_code == 422 and ledger.calls == []


def test_a_clean_crossing_still_decides_and_ledgers_once(rig):
    c, _, ledger = rig
    r = c.post("/crossing", content=crossing_json(counterparty_manifest="{}", request_summary='"héllo 日本"'), headers=H)
    assert r.status_code == 200 and r.json()["decision"] in ("BLOCK", "ALLOW")
    assert len(ledger.calls) == 1


def test_the_models_refuse_it_without_http_too():
    # R-PR711 condition 2: on main, the bounded `Name` / `max_length` fields refuse a lone surrogate in pydantic itself
    # (`string_unicode`) before this module's validator runs, so the refusal is asserted with no echo, not by wording.
    for build in (lambda: FederationContract(contract_id="x", counterparty_org="O", allowed_scopes=["a\ud800"],
                                             allowed_data_classes=["d"]),
                  lambda: CrossingRequest(counterparty_org="O", counterparty_agent_id="a", counterparty_manifest={},
                                          scope="s", data_class="d", request_summary="a\ud800")):
        with pytest.raises(ValueError) as e:
            build()
        assert "ud800" not in str(e.value) and "\ud800" not in str(e.value)


@pytest.mark.parametrize("manifest", [{"k": "a\ud800"}, {"a\ud800": "v"}, {"k": [{"deep": ["a\ud800"]}]}],
                         ids=["value", "key", "nested"])
def test_a_manifest_value_is_refused_by_this_modules_validator(manifest):
    """The gap main still leaves open: the manifest dict's contents. This module's walk refuses it, naming the field."""
    with pytest.raises(ValueError, match="counterparty_manifest holds text that is not valid UTF-8") as e:
        CrossingRequest(counterparty_org="O", counterparty_agent_id="a", counterparty_manifest=manifest,
                        scope="s", data_class="d")
    assert "ud800" not in str(e.value) and "\ud800" not in str(e.value)


def _nested(depth, leaf):
    v = leaf
    for _ in range(depth):
        v = [v]
    return v


def test_the_walk_has_no_recursion_limit():
    """R-PR711 condition 3: the walk is iterative, so depth never raises RecursionError (the recursive walk failed at
    about 500 levels; this goes far past the interpreter's default limit)."""
    from federation_broker.engine import _first_unencodable

    assert _first_unencodable(_nested(5000, "ok")) is False
    assert _first_unencodable(_nested(5000, "a\ud800")) is True
    assert _first_unencodable({"k": _nested(5000, {"a\ud800": 1})}) is True


@pytest.mark.parametrize("depth", [500, 900])
def test_a_deep_manifest_crossing_is_not_a_500(rig, depth):
    """R-PR711 condition 3, through the route: a counterparty_manifest nested `depth` lists deep must not 500 (the
    recursive walk 500'd from about 450). Main's own placeholder walk 500s from about 1200, so 900 is the pin."""
    c, _, _ = rig
    body = {"counterparty_org": COUNTERPARTY, "counterparty_agent_id": "a", "scope": "s", "data_class": "d",
            "counterparty_manifest": {"k": _nested(depth, "ok")}}
    r = c.post("/crossing", json=body)
    assert r.status_code != 500, (depth, r.status_code)
