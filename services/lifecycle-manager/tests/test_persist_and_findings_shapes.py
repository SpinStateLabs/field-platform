"""S4-11: (1) _persist wrote `<name>.json.tmp` for EVERY writer, so the scheduler thread and a served POST /sweep could
share one temp name and the second os.replace raised FileNotFoundError, a 500 after the sweep (and any auto-kill) had
already run. The temp name is unique per write and removed on failure. (2) GET /findings returned json.loads output
unchecked (a list or string was returned as is, or hit `{**data}` and raised) and its 500 detail leaked the server file
path (OSError text). A non-object file is unreadable, with a fixed detail. (3) SweepRequest.operator was min_length=1
only: a whitespace-only operator reached the kill reasons and ledger rows. It is stripped, blank is a 422, max 200."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lifecycle_manager import api as lapi
from lifecycle_manager.api import create_app

ROSTER = "owner\nAlice\n"
SECRET_DIR = "SECRET-SERVER-DIR"


class FakeRegistry:
    def list_agents(self, *a, **k):
        return []


class NoTokens:
    def get(self, path, *a, **k):
        return []


class Ledger:
    def append(self, event_type, payload=None, agent_id=None):
        return None


@pytest.fixture()
def served(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / SECRET_DIR))
    app = create_app(registry=FakeRegistry(), delegation=NoTokens(), ledger=Ledger(), every=0)
    return app, TestClient(app)


# ---- (1) _persist: a unique temp name ---------------------------------------------------------------------------------


def test_two_writers_interleaving_on_one_path_never_raise(tmp_path, monkeypatch):
    """Deterministic interleaving: while the OUTER persist is about to os.replace, a second writer persists to the same
    path (the scheduler thread vs a served POST /sweep). With one shared temp name the inner replace consumed it and
    the outer raised FileNotFoundError."""
    path = tmp_path / "lifecycle" / "last_sweep.json"
    real, state = os.replace, {"inner": False}

    def replace(src, dst):
        if not state["inner"]:
            state["inner"] = True
            lapi._persist(path, {"writer": "inner"})
        return real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    lapi._persist(path, {"writer": "outer"})                       # must not raise
    assert json.loads(path.read_text(encoding="utf-8"))["writer"] == "outer"
    assert [p.name for p in path.parent.iterdir()] == ["last_sweep.json"]      # no temp file left


def test_the_temp_name_differs_on_every_write(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle" / "last_sweep.json"
    seen, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (seen.append(Path(src).name), real(src, dst))[1])
    for i in range(5):
        lapi._persist(path, {"i": i})
    assert len(set(seen)) == 5 and all(n != "last_sweep.json" for n in seen)


def test_many_threads_writing_one_path_never_raise_and_leave_valid_json(tmp_path):
    path = tmp_path / "lifecycle" / "last_sweep.json"
    errors, barrier = [], threading.Barrier(8)

    def writer(n):
        barrier.wait()
        for i in range(60):
            try:
                lapi._persist(path, {"writer": n, "i": i})
            except BaseException as exc:                                    # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"writer", "i"}
    assert [p.name for p in path.parent.iterdir()] == ["last_sweep.json"]


def test_a_failed_replace_leaves_the_old_file_and_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle" / "last_sweep.json"
    lapi._persist(path, {"v": 1})

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        lapi._persist(path, {"v": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in path.parent.iterdir()] == ["last_sweep.json"]


def test_the_persisted_file_keeps_the_ordinary_umask_default_mode(tmp_path):
    """Not mkstemp's 0600: whatever reads last_sweep.json today keeps reading it."""
    plain = tmp_path / "plain.json"
    plain.write_text("{}", encoding="utf-8")
    persisted = tmp_path / "lifecycle" / "last_sweep.json"
    lapi._persist(persisted, {})
    assert (persisted.stat().st_mode & 0o777) == (plain.stat().st_mode & 0o777)


def test_a_persisted_payload_round_trips(tmp_path):
    path = tmp_path / "lifecycle" / "last_sweep.json"
    lapi._persist(path, {"a": [1, 2], "b": "é"})
    assert lapi._load(path) == {"a": [1, 2], "b": "é"}
    assert lapi._load(tmp_path / "missing.json") is None


# ---- (2) GET /findings ------------------------------------------------------------------------------------------------


def write(app, which, text):
    path = getattr(app.state, which)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("text", ["[]", '"x"', "123", "null", "true", "[1, 2]", "{bad json"])
@pytest.mark.parametrize("which", ["findings_path", "tick_path"])
def test_a_state_file_that_is_not_a_json_object_is_a_fixed_500_without_the_path(served, which, text):
    app, client = served
    write(app, "findings_path", '{"swept_at": "t"}')
    write(app, which, text)
    r = client.get("/findings")
    assert r.status_code == 500, r.text
    assert r.json()["detail"] == "lifecycle state unreadable"
    assert SECRET_DIR not in r.text


@pytest.mark.parametrize("which", ["findings_path", "tick_path"])
def test_a_directory_in_place_of_a_state_file_is_the_same_fixed_500(served, which):
    app, client = served
    write(app, "findings_path", '{"swept_at": "t"}')
    path = getattr(app.state, which)
    if path.exists():
        path.unlink()
    path.mkdir(parents=True)
    r = client.get("/findings")
    assert r.status_code == 500 and r.json()["detail"] == "lifecycle state unreadable"
    assert SECRET_DIR not in r.text


def test_findings_still_serves_a_real_report_with_the_last_tick(served):
    app, client = served
    write(app, "findings_path", '{"swept_at": "t", "orphans": []}')
    write(app, "tick_path", '{"skipped": "no roster"}')
    assert client.get("/findings").json() == {"swept_at": "t", "orphans": [], "last_tick": {"skipped": "no roster"}}


def test_findings_with_no_sweep_is_still_the_404_with_the_tick(served):
    app, client = served
    write(app, "tick_path", '{"skipped": "no roster"}')
    r = client.get("/findings")
    assert r.status_code == 404 and r.json()["detail"]["last_tick"] == {"skipped": "no roster"}


def test_a_real_served_sweep_is_persisted_and_read_back(served):
    app, client = served
    assert client.post("/sweep", json={"roster_csv": ROSTER}).status_code == 200
    got = client.get("/findings").json()
    assert "swept_at" in got and got["roster_size"] == 1
    assert [p.name for p in app.state.findings_path.parent.iterdir()] == ["last_sweep.json"]


# ---- (3) the operator -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("operator", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_a_blank_operator_is_a_422_and_nothing_is_swept_or_persisted(served, operator):
    app, client = served
    r = client.post("/sweep", json={"roster_csv": ROSTER, "operator": operator})
    assert r.status_code == 422, r.text
    assert not app.state.findings_path.exists()


def test_an_over_long_operator_is_a_422_and_the_bound_itself_is_accepted(served):
    _, client = served
    assert client.post("/sweep", json={"roster_csv": ROSTER, "operator": "o" * 201}).status_code == 422
    assert client.post("/sweep", json={"roster_csv": ROSTER, "operator": "o" * 200}).status_code == 200


def test_the_operator_is_stored_stripped_and_the_default_is_unchanged(served):
    _, client = served
    r = client.post("/sweep", json={"roster_csv": ROSTER, "operator": "  Don Hagell  "})
    assert r.status_code == 200 and r.json()["config"]["operator"] == "Don Hagell"
    r = client.post("/sweep", json={"roster_csv": ROSTER})
    assert r.json()["config"]["operator"] == "lifecycle-manager (served)"
