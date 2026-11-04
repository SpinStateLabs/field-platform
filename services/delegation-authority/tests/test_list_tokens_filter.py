"""`TokenStore.list` / `GET /tokens?agent_id=`: an empty agent_id matches nothing, never the whole table (scout P-9).

Before: `if agent_id:` treated the empty string like "no filter", so `GET /tokens?agent_id=` returned every token of every
agent (a caller that built the id from an empty variable got the whole table). Omitting the parameter is still the
unfiltered list (the lifecycle sweep and the ops-console read it that way)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken

BASE = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)


def _token(agent_id: str, *, issued_at: datetime = BASE, **kw) -> DelegationToken:
    base = dict(agent_id=agent_id, granted_by="Don Hagell, Spin State Labs", scope=["read timesheets"],
                issued_at=issued_at, expires_at=issued_at + timedelta(hours=1))
    base.update(kw)
    return DelegationToken(**base)


@pytest.fixture()
def store(tmp_path):
    s = TokenStore(tmp_path / "tokens.sqlite3")
    s.save(_token("alpha-agent"))
    s.save(_token("beta-agent"))
    yield s


def test_an_empty_agent_id_matches_nothing(store):
    assert store.list(agent_id="") == []


def test_no_agent_id_still_lists_everything(store):
    assert {t.agent_id for t in store.list()} == {"alpha-agent", "beta-agent"}
    assert {t.agent_id for t in store.list(agent_id=None)} == {"alpha-agent", "beta-agent"}


def test_an_unknown_agent_matches_nothing(store):
    assert store.list(agent_id="nobody-agent") == []


def test_a_known_agent_lists_its_active_and_its_revoked_token(tmp_path):
    s = TokenStore(tmp_path / "t.sqlite3")
    live = s.save(_token("alpha-agent"))
    dead = s.save(_token("alpha-agent", revoked=True, revocation_id="rev-1", revoked_at=BASE))
    s.save(_token("beta-agent"))
    got = s.list(agent_id="alpha-agent")
    assert {t.token_id for t in got} == {live.token_id, dead.token_id}
    assert {t.revoked for t in got} == {True, False}


def test_the_api_empty_agent_id_returns_an_empty_list(tmp_path):
    s = TokenStore(tmp_path / "t.sqlite3")
    s.save(_token("alpha-agent"))
    client = TestClient(create_app(store=s))
    assert client.get("/tokens", params={"agent_id": ""}).json() == []
    assert len(client.get("/tokens").json()) == 1
    assert len(client.get("/tokens", params={"agent_id": "alpha-agent"}).json()) == 1


def test_tokens_are_ordered_by_instant_across_utc_offsets(tmp_path):
    """ORDER BY is on the ISO text column: 06:00+00:00 sorts before 10:00+05:00 as text although 10:00+05:00 is 05:00Z,
    the earlier instant."""
    s = TokenStore(tmp_path / "t.sqlite3")
    plus5 = timezone(timedelta(hours=5))
    early = s.save(_token("alpha-agent", issued_at=datetime(2030, 1, 1, 10, 0, tzinfo=plus5)))     # 05:00Z
    late = s.save(_token("alpha-agent", issued_at=datetime(2030, 1, 1, 6, 0, tzinfo=timezone.utc)))  # 06:00Z
    assert [t.token_id for t in s.list(agent_id="alpha-agent")] == [early.token_id, late.token_id]
    assert [t.token_id for t in s.list()] == [early.token_id, late.token_id]
