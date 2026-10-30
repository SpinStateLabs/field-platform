"""C-625 (reviewer C-527 F-C527-1, -4, -5): revoke is ledger-first and idempotent in one step, and the OAuth
introspection endpoint matches a token id exactly."""

from __future__ import annotations

import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenNotFoundError, TokenStore
from field_core.delegation import DelegationToken
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

FORM = {"content-type": "application/x-www-form-urlencoded"}


class DownClient:
    def post(self, *a, **k):
        raise ConnectionError("ledger down")

    def get(self, *a, **k):
        raise ConnectionError("ledger down")


class SlowLedger:
    """Delegates to the real ledger client after a pause, so concurrent revokes overlap inside the append."""

    def __init__(self, inner, pause=0.08):
        self._inner, self._pause = inner, pause

    def append(self, *a, **k):
        time.sleep(self._pause)
        return self._inner.append(*a, **k)


@pytest.fixture()
def world(tmp_path):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger_http = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    ledger = LedgerClient(client=ledger_http, base_url="http://testserver")
    store = TokenStore(tmp_path / "tokens.sqlite3")
    app = create_delegation_app(store=store, ledger=ledger, registry=RegistryClient(client=registry, base_url="http://testserver"))
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoice Copilot", "owner": "Controller", "domain": "finance"})
    return TestClient(app), app, store, ledger_http, ledger


def mint(delegation):
    r = delegation.post("/tokens", json={"agent_id": "invoicing-agent", "granted_by": "Controller",
                                         "scope": ["read timesheets"], "ttl_seconds": 3600})
    assert r.status_code in (200, 201), r.text
    return r.json()["token_id"]


def revoke_events(ledger_http):
    return ledger_http.get("/events", params={"event_type": "delegation.revoke"}).json()


# --- F-C527-1: a revoke during a ledger outage is refused -----------------------------------------------------------


def test_a_revoke_while_the_ledger_is_down_is_refused_502_and_the_token_stays_active(world):
    delegation, app, store, ledger_http, _ = world
    token_id = mint(delegation)
    app.state.ledger = LedgerClient(client=DownClient(), base_url="http://testserver")
    r = delegation.post(f"/tokens/{token_id}/revoke")
    assert r.status_code == 502 and "refusing to revoke" in r.json()["detail"]
    assert store.get(token_id).revoked is False
    assert delegation.post("/introspect", json={"token_id": token_id}).json()["active"] is True
    assert revoke_events(ledger_http) == []


def test_after_the_ledger_is_back_the_same_revoke_succeeds(world):
    delegation, app, store, ledger_http, ledger = world
    token_id = mint(delegation)
    app.state.ledger = LedgerClient(client=DownClient(), base_url="http://testserver")
    assert delegation.post(f"/tokens/{token_id}/revoke").status_code == 502
    app.state.ledger = ledger
    assert delegation.post(f"/tokens/{token_id}/revoke").status_code == 200
    assert store.get(token_id).revoked is True and len(revoke_events(ledger_http)) == 1


# --- F-C527-4: one revocation, one event -------------------------------------------------------------------------------


def test_concurrent_revokes_of_one_token_return_one_revocation_id_and_write_one_event(world):
    delegation, app, store, ledger_http, ledger = world
    app.state.ledger = SlowLedger(ledger)
    token_id = mint(delegation)
    results, barrier = [], threading.Barrier(8)

    def go():
        barrier.wait()
        results.append(delegation.post(f"/tokens/{token_id}/revoke"))

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert [r.status_code for r in results] == [200] * 8
    ids = {r.json()["revocation_id"] for r in results}
    assert len(ids) == 1 and None not in ids
    assert store.get(token_id).revocation_id == ids.pop()
    assert len(revoke_events(ledger_http)) == 1


def test_a_second_revoke_returns_the_first_revocation_id_and_no_second_event(world):
    delegation, _, store, ledger_http, _ = world
    token_id = mint(delegation)
    first = delegation.post(f"/tokens/{token_id}/revoke").json()
    second = delegation.post(f"/tokens/{token_id}/revoke").json()
    assert first["revocation_id"] == second["revocation_id"] and second["revoked"] is True
    assert len(revoke_events(ledger_http)) == 1


def test_revoking_an_unknown_token_is_404_and_writes_nothing(world):
    delegation, _, _, ledger_http, _ = world
    assert delegation.post("/tokens/no-such-token/revoke").status_code == 404
    assert revoke_events(ledger_http) == []


def _token(store, tmp_id="t-1"):
    now = datetime.now(timezone.utc)
    return store.save(DelegationToken(token_id=tmp_id, agent_id="a", granted_by="g", scope=["x"], issued_at=now,
                                      expires_at=now + timedelta(hours=1)))


def test_save_revoked_revokes_once_and_the_loser_gets_the_winners_row(tmp_path):
    store = TokenStore(tmp_path / "t.sqlite3")
    token = _token(store)
    a, b = token.revoke(), token.revoke()
    assert a.revocation_id != b.revocation_id
    stored_a, won_a = store.save_revoked(a)
    stored_b, won_b = store.save_revoked(b)
    assert won_a is True and won_b is False
    assert stored_a.revocation_id == a.revocation_id and stored_b.revocation_id == a.revocation_id
    assert store.get("t-1").revocation_id == a.revocation_id and store.get("t-1").revoked is True


def test_save_revoked_of_an_unknown_token_raises(tmp_path):
    store = TokenStore(tmp_path / "t.sqlite3")
    now = datetime.now(timezone.utc)
    ghost = DelegationToken(token_id="ghost", agent_id="a", granted_by="g", scope=["x"], issued_at=now,
                            expires_at=now + timedelta(hours=1)).revoke()
    with pytest.raises(TokenNotFoundError):
        store.save_revoked(ghost)


def test_save_revoked_keeps_the_spend_ceiling_of_the_token(tmp_path):
    store = TokenStore(tmp_path / "t.sqlite3")
    now = datetime.now(timezone.utc)
    capped = store.save(DelegationToken(token_id="c-1", agent_id="a", granted_by="g", scope=["x"], issued_at=now,
                                        expires_at=now + timedelta(hours=1), max_spend_usd=2.5))
    stored, won = store.save_revoked(capped.revoke())
    assert won is True and stored.max_spend_usd == 2.5


# --- F-C527-5: /oauth/introspect matches the id exactly -----------------------------------------------------------------


def oauth(delegation, token):
    return delegation.post("/oauth/introspect", content=urllib.parse.urlencode({"token": token}), headers=FORM)


def test_an_exact_token_id_is_active_and_a_padded_one_is_unknown(world):
    delegation, *_ = world
    token_id = mint(delegation)
    assert oauth(delegation, token_id).json()["active"] is True
    for padded in (f" {token_id}", f"{token_id} ", f"  {token_id}  ", f"\t{token_id}\n"):
        r = oauth(delegation, padded)
        assert r.status_code == 200 and r.json() == {"active": False}, repr(padded)


def test_the_two_introspection_routes_agree_on_a_padded_id(world):
    delegation, *_ = world
    token_id = mint(delegation)
    padded = f" {token_id} "
    assert delegation.post("/introspect", json={"token_id": padded}).json()["active"] is False
    assert oauth(delegation, padded).json() == {"active": False}


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n"])
def test_an_empty_or_blank_token_field_is_still_400(world, blank):
    delegation, *_ = world
    assert oauth(delegation, blank).status_code == 400


# --- the write is conditional: a second PROCESS cannot overwrite the first one's revocation id -------------------------


def test_a_revoke_that_loses_a_cross_process_race_returns_the_winners_revocation_id(tmp_path):
    """Two apps (two stores, so two locks, as two processes would have) over one database file. App A is paused in its
    ledger append while app B revokes the same token completely; when A resumes its write must not replace B's
    revocation id (`UPDATE ... WHERE revoked=0`), and A answers with B's."""
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger_http = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    real = LedgerClient(client=ledger_http, base_url="http://testserver")
    reg = RegistryClient(client=registry, base_url="http://testserver")
    db = tmp_path / "tokens.sqlite3"
    app_b = create_delegation_app(store=TokenStore(db), ledger=real, registry=reg)
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoice Copilot", "owner": "Controller", "domain": "finance"})
    client_b = TestClient(app_b)
    token_id = mint(client_b)
    seen = {}

    class PausedLedger:
        def append(self, *a, **k):
            if not seen:                                              # the first append only: B revokes in the gap
                seen["b"] = client_b.post(f"/tokens/{token_id}/revoke").json()
            return real.append(*a, **k)

    app_a = create_delegation_app(store=TokenStore(db), ledger=PausedLedger(), registry=reg)
    answer_a = TestClient(app_a).post(f"/tokens/{token_id}/revoke")
    assert answer_a.status_code == 200
    winner = seen["b"]["revocation_id"]
    assert answer_a.json()["revocation_id"] == winner
    assert TokenStore(db).get(token_id).revocation_id == winner
