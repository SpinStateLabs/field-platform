"""A mint request takes an agent id inside the registry's id rule only; a revoke is recorded for any stored token."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from delegation_authority.api import MintRequest, create_app
from delegation_authority.store import TokenStore
from field_core import operator_auth as oa
from field_core.delegation import DelegationToken

VALID = ["invoicing-agent", "a", "a..b_c-", "a" * 128]
INVALID = ["", "A", "-a", ".a", "a b", "a/b", "a?b", "a#b", "a%2Fb", "a" + chr(10), "a" + chr(0x202E), "a" * 129]


def _mint(agent_id):
    return MintRequest(agent_id=agent_id, granted_by="Grantor", scope=["act"], ttl_seconds=60)


@pytest.mark.parametrize("agent_id", VALID)
def test_a_valid_id_is_accepted_unchanged(agent_id):
    assert _mint(agent_id).agent_id == agent_id


@pytest.mark.parametrize("agent_id", INVALID)
def test_an_id_outside_the_rule_is_refused(agent_id):
    with pytest.raises(ValidationError):
        _mint(agent_id)


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload=None, agent_id=None):
        self.rows.append((event_type, agent_id))


@pytest.mark.parametrize("stored,keyed", [("invoicing-agent", "invoicing-agent"), ("Not Valid", None),
                                          ("a" * 201, None)], ids=["valid", "outside", "over-long"])
def test_a_revoke_row_is_keyed_only_by_an_id_inside_the_rule(tmp_path, monkeypatch, stored, keyed):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE):
        monkeypatch.delenv(name, raising=False)
    store, ledger = TokenStore(tmp_path / "t.sqlite3"), Ledger()
    now = datetime.now(timezone.utc)
    token = store.save(DelegationToken(agent_id=stored, granted_by="Grantor", scope=["act"], issued_at=now,
                                       expires_at=now + timedelta(hours=1)))
    client = TestClient(create_app(store=store, ledger=ledger, registry=object()))
    r = client.post(f"/tokens/{token.token_id}/revoke")
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] is True
    assert ledger.rows == [("delegation.revoke", keyed)]


class MintRegistry:
    def __init__(self, record):
        self.record, self.calls = record, []

    def require_active_agent(self, agent_id):
        self.calls.append(agent_id)
        return dict(self.record)


def _mint_app(tmp_path, monkeypatch, record):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, "FIELD_DOA_ROSTER"):
        monkeypatch.delenv(name, raising=False)
    store, ledger, registry = TokenStore(tmp_path / "t.sqlite3"), Ledger(), MintRegistry(record)
    return TestClient(create_app(store=store, ledger=ledger, registry=registry)), store, ledger, registry


def _body(agent_id):
    return {"agent_id": agent_id, "granted_by": "Grantor", "scope": ["act"], "ttl_seconds": 60}


@pytest.mark.parametrize("agent_id", INVALID)
def test_a_mint_for_an_id_outside_the_rule_reaches_no_registry_ledger_or_store(tmp_path, monkeypatch, agent_id):
    client, store, ledger, registry = _mint_app(tmp_path, monkeypatch, {"agent_id": "record-agent"})
    r = client.post("/tokens", json=_body(agent_id))
    assert r.status_code == 422, r.text
    assert registry.calls == [] and ledger.rows == [] and store.count() == 0


@pytest.mark.parametrize("record,keyed", [({"agent_id": "record-agent"}, "record-agent"), ({}, "asked-agent"),
                                          ({"agent_id": "Not Valid"}, "asked-agent")],
                         ids=["record", "no-id-in-record", "record-id-outside"])
def test_the_mint_row_is_keyed_by_the_registry_records_id(tmp_path, monkeypatch, record, keyed):
    client, store, ledger, registry = _mint_app(tmp_path, monkeypatch, record)
    r = client.post("/tokens", json=_body("asked-agent"))
    assert r.status_code == 201, r.text
    assert registry.calls == ["asked-agent"] and ledger.rows == [("delegation.mint", keyed)]
