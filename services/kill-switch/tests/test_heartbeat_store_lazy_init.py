"""The lazily built HeartbeatStore is built exactly ONCE per app.

v1.2 hardening, OPEN-B. ``create_app`` builds the store on the first
check-in, not at startup (a kill-switch nobody checks in to must create no
file -- pinned in test_endpoint_and_liveness.py). The old ``_hb_store()``
tested ``app.state.heartbeats is None`` and built a store with no
synchronisation, so concurrent first check-ins each built their own
``HeartbeatStore``: one sqlite3 connection and one ``_lock`` apiece, writing
the same file. The store's lock then serialised nothing across them, and all
but the last store were dropped with their connections still open
(reproduced in 23-30 of 30 barrier trials, up to 8 stores in one trial).

Each trial releases ``THREADS`` first check-ins together with a barrier on a
fresh app. The counting store sleeps inside ``__init__`` before the real
constructor runs, which holds the check-then-build window open so an
unsynchronised ``_hb_store`` builds more than one store every trial rather
than most trials. It adds no behaviour: the real ``HeartbeatStore`` is built
and used. Bounded: fixed thread and trial counts, and one shared join
deadline that turns a deadlock into a failure.
"""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

import kill_switch.api as kill_api
from kill_switch.store import HeartbeatStore

THREADS = 8
TRIALS = 5
BUILD_DELAY_S = 0.05
JOIN_DEADLINE_S = 60


class _Registry:
    """Every agent is registered and active; the check-in path only reads."""

    def get_agent(self, agent_id: str) -> dict:
        return {"agent_id": agent_id, "status": "active", "domain": "d",
                "name": agent_id, "owner": "o"}


class _Ledger:
    def append(self, *args, **kwargs) -> None:  # check-ins never ledger
        return None


def test_concurrent_first_checkins_build_exactly_one_heartbeat_store(
    tmp_path, monkeypatch
):
    built: list[HeartbeatStore] = []
    built_guard = threading.Lock()

    class CountingStore(HeartbeatStore):
        def __init__(self, path):
            with built_guard:
                built.append(self)
            time.sleep(BUILD_DELAY_S)
            super().__init__(path)

    monkeypatch.setattr(kill_api, "HeartbeatStore", CountingStore)

    failures: list[str] = []
    for trial in range(TRIALS):
        data_dir = tmp_path / f"trial-{trial}"
        monkeypatch.setenv("FIELD_DATA_DIR", str(data_dir))
        built.clear()
        app = kill_api.create_app(registry=_Registry(), ledger=_Ledger())
        assert app.state.heartbeats is None  # still lazy: nothing built yet
        clients = [TestClient(app) for _ in range(THREADS)]
        barrier = threading.Barrier(THREADS)
        codes: list[int] = []
        errors: list[str] = []

        def checkin(k: int) -> None:
            try:
                barrier.wait()
                codes.append(clients[k].post(f"/heartbeat/agent-{k}").status_code)
            except Exception as exc:  # recorded, asserted below
                errors.append(f"{type(exc).__name__}: {exc}")

        pool = [threading.Thread(target=checkin, args=(k,), daemon=True)
                for k in range(THREADS)]
        for t in pool:
            t.start()
        deadline = time.monotonic() + JOIN_DEADLINE_S
        for t in pool:
            t.join(max(0.0, deadline - time.monotonic()))
        hung = sum(t.is_alive() for t in pool)
        assert not hung, f"trial {trial}: {hung} check-in thread(s) still running: deadlock"

        store = app.state.heartbeats
        rows = store.all() if store is not None else {}
        checkins = sum(r["checkins"] for r in rows.values())
        if (len(built) != 1 or store is not built[0] or errors
                or sorted(codes) != [200] * THREADS or checkins != THREADS):
            failures.append(
                f"trial {trial}: stores built={len(built)} errors={errors[:2]} "
                f"codes={sorted(codes)} checkins={checkins}"
            )
        for extra in built:
            try:
                extra.close()
            except Exception:
                pass
    assert not failures, f"{len(failures)} of {TRIALS} trials: {failures}"
