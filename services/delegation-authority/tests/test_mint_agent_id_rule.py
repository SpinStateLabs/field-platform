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
