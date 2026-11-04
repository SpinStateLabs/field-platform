"""POST /export: a NUL byte in out_dir is a 422, and an I/O failure answers a 500 whose body
carries the errno NAME and never the server path (scout S-C7). Before: the NUL raised
ValueError out of Path.resolve/mkdir (a bare 500), and `detail=str(exc)` put the server's
absolute path into the response ("[Errno 2] No such file or directory: '/srv/...'")."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    c = TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")),
                   raise_server_exceptions=False)
    c.post("/events", json={"event_type": "x", "payload": {}})
    return c


@pytest.mark.parametrize("bad", ["a\x00b", "\x00", "/tmp/ok/\x00/x", "x\x00"])
def test_a_nul_in_out_dir_is_422_and_writes_nothing(client, tmp_path, bad):
    r = client.post("/export", params={"out_dir": bad})
    assert r.status_code == 422, r.text
    assert "out_dir" in r.json()["detail"]
    assert not any(p.name == "exports" for p in tmp_path.iterdir())


def test_an_io_failure_is_500_with_the_errno_name_and_no_server_path(client, tmp_path):
    blocker = tmp_path / "a-regular-file"
    blocker.write_text("x", encoding="utf-8")
    r = client.post("/export", params={"out_dir": str(blocker / "sub")})
    assert r.status_code == 500, r.text
    detail = r.json()["detail"]
    assert str(tmp_path) not in r.text and "a-regular-file" not in r.text
    assert detail.startswith("export failed (") and "ENOTDIR" in detail


def test_a_missing_parent_never_leaks_the_path(client, tmp_path):
    ro = tmp_path / "nope" / "deeper"
    r = client.post("/export", params={"out_dir": str(ro)})
    if r.status_code == 500:                     # a platform that cannot create the tree
        assert str(tmp_path) not in r.text
    else:
        assert r.status_code == 200


def test_a_normal_export_still_works(client, tmp_path):
    r = client.post("/export", params={"out_dir": str(tmp_path / "out")})
    assert r.status_code == 200, r.text
    assert (tmp_path / "out").is_dir()
