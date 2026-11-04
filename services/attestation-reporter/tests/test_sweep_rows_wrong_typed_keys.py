"""S6-12: a lifecycle.* event whose payload.token_id (or agent_id) is not a string must not crash
the pack. The ledger accepts any dict payload on a lifecycle.* type, so a list or dict key is
reachable. Such a key is counted as 'without <key>', never put in the distinct set."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from attestation_reporter.api import create_app
from attestation_reporter.engine import PackEngine
from field_core.authn import ENV_VAR
from field_core.ledger import GENESIS_HASH, make_event
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

EXPIRING = "Expiring authority (sweep events)"
DISTINCT_TOKENS = "Distinct tokens flagged as expiring"
REATTEST = "Re-attestation due (sweep events)"
DISTINCT_AGENTS = "Distinct agents flagged for re-attestation"
TS = "2026-07-02T06:00:00+00:00"


@pytest.fixture(autouse=True)
def _no_secret(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


def _engine(tmp_path, rows):
    events, prev = [], GENESIS_HASH
    for event_type, agent_id, payload in rows:
        ev = make_event(event_type, payload, prev_hash=prev, agent_id=agent_id, ts=TS)
        events.append(ev)
        prev = ev.hash
    path = tmp_path / "ledger" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")
    return PackEngine(ledger=TestClient(create_ledger_app(store=LedgerStore(path))))


def _by_name(pack):
    return {m.name: m for m in pack.all_metrics()}


@pytest.mark.parametrize("bad", [["a"], {"x": 1}, 7, True])
def test_a_wrong_typed_token_id_is_counted_as_missing_not_crashed(tmp_path, bad):
    engine = _engine(tmp_path, [
        ("lifecycle.expiring_authority", "fin-agent", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "fin-agent", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "crm-agent", {"token_id": bad}),
    ])
    m = _by_name(engine.build(period="2026-Q3"))
    assert m[EXPIRING].value == 3
    assert m[DISTINCT_TOKENS].value == 1
    assert "1 event(s) without payload.token_id not counted" in m[DISTINCT_TOKENS].note


def test_a_nested_token_id_is_counted_as_missing(tmp_path):
    engine = _engine(tmp_path, [
        ("lifecycle.expiring_authority", "fin-agent", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "crm-agent", {"token_id": {"nested": ["x"]}}),
    ])
    m = _by_name(engine.build(period="2026-Q3"))
    assert m[DISTINCT_TOKENS].value == 1


def test_string_keys_are_unchanged_and_the_other_rows_are_unaffected(tmp_path):
    engine = _engine(tmp_path, [
        ("lifecycle.reattestation_due", "fin-agent", {"days_stale": 91}),
        ("lifecycle.reattestation_due", "fin-agent", {"days_stale": 92}),
        ("lifecycle.expiring_authority", "a", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "b", {"token_id": "t-2"}),
        ("lifecycle.expiring_authority", "c", {"token_id": ["t-3"]}),
    ])
    m = _by_name(engine.build(period="2026-Q3"))
    assert (m[REATTEST].value, m[DISTINCT_AGENTS].value) == (2, 1)
    assert (m[EXPIRING].value, m[DISTINCT_TOKENS].value) == (3, 2)


def test_get_pack_answers_200_not_500(tmp_path):
    engine = _engine(tmp_path, [
        ("lifecycle.expiring_authority", "fin-agent", {"token_id": ["a"]}),
        ("lifecycle.expiring_authority", "crm-agent", {"token_id": {"x": 1}}),
    ])
    api = TestClient(create_app(engine=engine), raise_server_exceptions=False)
    r = api.get("/pack", params={"period": "2026-Q3"})
    assert r.status_code == 200, r.text
