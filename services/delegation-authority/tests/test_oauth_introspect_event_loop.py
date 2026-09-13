"""POST /oauth/introspect must not wait on the token store ON the event loop.

v1.2 hardening, OPEN-C. ``oauth_introspect`` is ``async def`` (it reads the
raw form body), and it called the synchronous ``TokenStore.get`` directly.
``get`` takes the store's ``threading.Lock``, which another request thread
can hold (a commit, a ``list()`` for /health or GET /tokens). While the
handler waited for that lock the event loop could run nothing else, so every
other request to the service -- including the async authn middleware in
front of every route -- stalled until the lock came free. Reproduced: with
the lock held for 3 s, an unrelated request took 3.0 s in 5 of 5 trials.

The test uses ONE ``TestClient`` as a context manager, so every request runs
on one event loop, as under uvicorn (without the context manager each
request gets its own loop and a stall cannot be observed). It holds the
store lock in this thread, sends an introspection (which must now wait in a
worker thread), and while the lock is still held requests
``GET /openapi.json``: FastAPI's own async route, which touches no store and
needs only a free loop. The probe is not ``/health`` because this service's
``/health`` counts tokens through ``TokenStore.list()`` and so waits on the
same lock by design, loop or no loop.

The ``SignallingStore`` only sets an event when ``get`` is entered, so the
probe is sent after the handler has reached the store; ``get`` itself is the
real locked method. Bounded: the lock is released after ``PROBE_BOUND_S``
whether or not the probe answered, and every join has a timeout.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
PROBE_BOUND_S = 5.0
JOIN_TIMEOUT_S = 30


class _Unused:
    """Ledger and registry: /oauth/introspect and /openapi.json use neither."""


def test_introspection_waiting_on_the_store_lock_does_not_stall_other_requests(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    entered = threading.Event()

    class SignallingStore(TokenStore):
        def get(self, token_id: str) -> DelegationToken:
            entered.set()
            return super().get(token_id)

    store = SignallingStore(tmp_path / "tokens.sqlite3")
    now = datetime.now(timezone.utc)
    token = store.save(DelegationToken(
        agent_id="invoicing-agent", granted_by="Controller", scope=["read timesheets"],
        issued_at=now, expires_at=now + timedelta(hours=1),
    ))
    app = create_app(store=store, ledger=_Unused(), registry=_Unused())

    result: dict[str, object] = {}
    lock_held = [False]
    try:
        with TestClient(app) as client:
            assert client.get("/openapi.json").status_code == 200  # warm, unlocked

            def introspect() -> None:
                r = client.post("/oauth/introspect",
                                content=f"token={token.token_id}", headers=FORM)
                result["introspect"] = (r.status_code, r.json())

            def probe() -> None:
                r = client.get("/openapi.json")
                result["probe_status"] = r.status_code
                result["probe_answered_while_lock_held"] = lock_held[0]

            store._lock.acquire()
            lock_held[0] = True
            try:
                waiter = threading.Thread(target=introspect, daemon=True)
                waiter.start()
                assert entered.wait(JOIN_TIMEOUT_S), "introspection never reached the store"
                prober = threading.Thread(target=probe, daemon=True)
                prober.start()
                prober.join(PROBE_BOUND_S)
            finally:
                lock_held[0] = False
                store._lock.release()
            waiter.join(JOIN_TIMEOUT_S)
            prober.join(JOIN_TIMEOUT_S)
            assert not waiter.is_alive() and not prober.is_alive(), "request hung after release"
    finally:
        store.close()

    assert result.get("probe_answered_while_lock_held") is True, (
        f"GET /openapi.json did not answer within {PROBE_BOUND_S} s while "
        "/oauth/introspect waited on the token-store lock: the event loop was "
        f"stalled (result={result})"
    )
    assert result["probe_status"] == 200
    # The introspection itself still completes correctly once the lock frees.
    status, body = result["introspect"]
    assert status == 200 and body["active"] is True and body["sub"] == "invoicing-agent"


def test_introspection_of_an_unknown_token_is_still_exactly_inactive(tmp_path, monkeypatch):
    """The store call moved into a worker thread: ``TokenNotFoundError`` must
    still cross back and become exactly ``{"active": false}``."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = TokenStore(tmp_path / "tokens.sqlite3")
    try:
        client = TestClient(create_app(store=store, ledger=_Unused(), registry=_Unused()))
        r = client.post("/oauth/introspect", content="token=no-such-token", headers=FORM)
        assert r.status_code == 200
        assert r.json() == {"active": False}
    finally:
        store.close()
