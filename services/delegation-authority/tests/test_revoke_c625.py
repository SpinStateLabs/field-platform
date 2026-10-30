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
    delegation, app, _, ledger_http, _ = world
    assert delegation.post("/tokens/no-such-token/revoke").status_code == 404
    assert revoke_events(ledger_http) == []
    # C-821 (reviewer C-692 F-C692-2a): as a RESPONSE, not an exception the test client re-raises: a bare `raise` in
    # the handler would be a 500 here
    quiet = TestClient(app, raise_server_exceptions=False)
    for bad in ("no-such-token", "a%2Fb", "x" * 300):
        r = quiet.post(f"/tokens/{bad}/revoke")
        assert r.status_code == 404 and "not found" in r.json()["detail"], bad
    assert revoke_events(ledger_http) == []


@pytest.mark.parametrize("status", [401, 403, 422, 500])
def test_a_ledger_that_answers_with_an_error_is_a_refusal_not_an_outage(world, status):
    """C-821 (reviewer C-692 F-C692-3): still 502 and the token stays active, but the message says the ledger refused."""
    from field_core.clients import LedgerUnreachableError

    class Refusing:
        def append(self, *a, **k):
            raise LedgerUnreachableError("body must not be echoed", status_code=status)

    delegation, app, store, ledger_http, _ = world
    token_id = mint(delegation)
    app.state.ledger = Refusing()
    r = delegation.post(f"/tokens/{token_id}/revoke")
    assert r.status_code == 502 and r.json()["detail"] == f"ledger refused (HTTP {status}) — refusing to revoke"
    assert store.get(token_id).revoked is False and revoke_events(ledger_http) == []


def test_a_ledger_that_cannot_be_reached_still_says_unreachable(world):
    from field_core.clients import LedgerUnreachableError

    class Down:
        def append(self, *a, **k):
            raise LedgerUnreachableError("no route")

    delegation, app, store, _, _ = world
    token_id = mint(delegation)
    app.state.ledger = Down()
    r = delegation.post(f"/tokens/{token_id}/revoke")
    assert r.status_code == 502 and r.json()["detail"].startswith("ledger unreachable")
    assert store.get(token_id).revoked is False


def _token(store, tmp_id="t-1"):
    now = datetime.now(timezone.utc)
    return store.save(DelegationToken(token_id=tmp_id, agent_id="a", granted_by="g", scope=["x"], issued_at=now,
                                      expires_at=now + timedelta(hours=1)))


def test_save_revoked_revokes_once_and_the_loser_gets_the_winners_row(tmp_path):
    store = TokenStore(tmp_path / "t.sqlite3")
    token = _token(store)
    a, b = token.revoke(), token.revoke()
    assert a.revocation_id != b.revocation_id
    stored_a = store.save_revoked(a)
    stored_b = store.save_revoked(b)
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
    stored = store.save_revoked(capped.revoke())
    assert stored.revoked is True and stored.max_spend_usd == 2.5


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
    # C-821 (reviewer C-692 F-C692-2b): the loser answers with the STORED row, timestamp included, not its own
    assert answer_a.json()["revoked_at"] == seen["b"]["revoked_at"] == TokenStore(db).get(token_id).revoked_at.isoformat()


# --- C-725 (reviewer C-701): a stable revocation id, a per-token lock ---------------------------------------------------

from delegation_authority.api import _KeyedLocks, stable_revocation_id  # noqa: E402


def test_the_revocation_id_is_a_function_of_the_token_id():
    a, b = stable_revocation_id("tok-a"), stable_revocation_id("tok-b")
    assert a == stable_revocation_id("tok-a") and a != b
    assert len(a) == 36 and a.count("-") == 4


def test_a_revoke_retried_after_a_crash_between_the_ledger_and_the_store_reuses_the_same_id(world):
    delegation, app, store, ledger_http, _ = world
    token_id = mint(delegation)
    real = store.save_revoked
    calls = {"n": 0}

    def crash_once(token):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash between the ledger and the store")
        return real(token)

    store.save_revoked = crash_once
    with pytest.raises(RuntimeError):
        delegation.post(f"/tokens/{token_id}/revoke")
    assert store.get(token_id).revoked is False                       # the event is written, the token is still active
    assert delegation.post("/introspect", json={"token_id": token_id}).json()["active"] is True
    r = delegation.post(f"/tokens/{token_id}/revoke")                  # the retry
    assert r.status_code == 200 and r.json()["revoked"] is True
    ids = {e["payload"]["revocation_id"] for e in revoke_events(ledger_http)}
    assert len(revoke_events(ledger_http)) == 2                       # at least once: a repeat event is allowed
    assert ids == {stable_revocation_id(token_id)}                    # ... with the SAME id, never a second one
    assert store.get(token_id).revocation_id == stable_revocation_id(token_id)


def test_every_event_carries_an_id_the_token_stores_after_a_two_process_race(tmp_path):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger_http = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    real = LedgerClient(client=ledger_http, base_url="http://testserver")
    reg = RegistryClient(client=registry, base_url="http://testserver")
    db = tmp_path / "tokens.sqlite3"
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoice Copilot", "owner": "Controller", "domain": "finance"})
    gate = threading.Barrier(2)

    class Meet:
        def append(self, event_type, payload=None, agent_id=None, **k):
            if event_type == "delegation.revoke":
                gate.wait(timeout=10)                                  # both processes are inside the ledger call
            return real.append(event_type, payload=payload, agent_id=agent_id, **k)

    app_a = create_delegation_app(store=TokenStore(db), ledger=Meet(), registry=reg)
    app_b = create_delegation_app(store=TokenStore(db), ledger=Meet(), registry=reg)
    token_id = mint(TestClient(app_a))
    out = []
    threads = [threading.Thread(target=lambda a=a: out.append(TestClient(a).post(f"/tokens/{token_id}/revoke"))) for a in (app_a, app_b)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert [r.status_code for r in out] == [200, 200]
    events = revoke_events(ledger_http)
    assert len(events) == 2                                            # both appended: the documented repeat
    stored = TokenStore(db).get(token_id).revocation_id
    assert {e["payload"]["revocation_id"] for e in events} == {stored} == {r.json()["revocation_id"] for r in out}


def test_a_slow_ledger_append_for_one_token_does_not_block_the_revoke_of_another(world):
    delegation, app, store, ledger_http, ledger = world
    first, second = mint(delegation), mint(delegation)
    inside, release = threading.Event(), threading.Event()

    class Gated:
        def append(self, event_type, payload=None, agent_id=None, **k):
            if payload and payload.get("token_id") == first:
                inside.set()
                assert release.wait(10), "the first revoke was never released"
            return ledger.append(event_type, payload=payload, agent_id=agent_id, **k)

    app.state.ledger = Gated()
    done = {}
    t = threading.Thread(target=lambda: done.setdefault("first", delegation.post(f"/tokens/{first}/revoke")))
    t.start()
    assert inside.wait(10)                                             # the first revoke is parked INSIDE the ledger call
    other = delegation.post(f"/tokens/{second}/revoke")                # a global lock would hang here until the timeout
    assert other.status_code == 200 and "first" not in done
    release.set()
    t.join(10)
    assert done["first"].status_code == 200


def test_two_revokes_of_the_same_token_still_run_one_at_a_time(world):
    delegation, app, store, ledger_http, ledger = world
    token_id = mint(delegation)
    inside, release, order = threading.Event(), threading.Event(), []

    class Gated:
        def append(self, event_type, payload=None, agent_id=None, **k):
            order.append("append")
            inside.set()
            assert release.wait(10)
            return ledger.append(event_type, payload=payload, agent_id=agent_id, **k)

    app.state.ledger = Gated()
    results = []
    first = threading.Thread(target=lambda: results.append(delegation.post(f"/tokens/{token_id}/revoke")))
    first.start()
    assert inside.wait(10)
    second = threading.Thread(target=lambda: results.append(delegation.post(f"/tokens/{token_id}/revoke")))
    second.start()
    second.join(0.3)
    assert second.is_alive() and order == ["append"]                   # the second waits on the token's lock
    release.set()
    first.join(10)
    second.join(10)
    assert [r.status_code for r in results] == [200, 200] and order == ["append"]   # and then finds it revoked: no 2nd event
    assert len(revoke_events(ledger_http)) == 1


def test_the_keyed_locks_are_dropped_when_nobody_holds_or_waits_for_them():
    locks = _KeyedLocks()
    with locks.hold("a"):
        with locks.hold("b"):
            assert set(locks._entries) == {"a", "b"}
    assert locks._entries == {}


def test_the_keyed_locks_exclude_one_key_and_not_two():
    locks = _KeyedLocks()
    entered, release, got = threading.Event(), threading.Event(), []

    def hold_a():
        with locks.hold("a"):
            entered.set()
            release.wait(10)

    t = threading.Thread(target=hold_a)
    t.start()
    assert entered.wait(10)
    with locks.hold("b"):
        got.append("b")                                                # another key is not blocked
    waiter = threading.Thread(target=lambda: (locks.hold("a").__enter__(), got.append("a")))
    waiter.daemon = True
    waiter.start()
    waiter.join(0.2)
    assert got == ["b"]                                                # the same key waits
    release.set()
    t.join(10)
    waiter.join(10)
    assert got == ["b", "a"]


def test_the_guarantee_is_stated_in_the_code():
    import inspect

    from delegation_authority import api

    assert "AT LEAST ONE" in inspect.getsource(api)
    assert "SAME id" in stable_revocation_id.__doc__ and "at least once" in stable_revocation_id.__doc__


def test_the_readme_and_the_code_say_the_revoke_event_means_requested():
    """C-821 (reviewer C-692 F-C692-1): the repeat and the crash window are stated where a reader looks."""
    from pathlib import Path

    import delegation_authority.api as api

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert 'means "revoke REQUESTED"' in readme and "nothing sweeps those for you" in readme
    assert "ledger refused (HTTP n)" in readme
    source = Path(api.__file__).read_text(encoding="utf-8")
    assert '"revoke REQUESTED"' in source and "named out of scope" in source
