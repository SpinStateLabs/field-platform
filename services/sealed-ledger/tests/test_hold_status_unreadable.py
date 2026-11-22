"""S10-22: `GET /hold` on an unreadable hold marker is a 503 that names the exception CLASS, never the server path.

`hold_status()` answered `503 ledger busy: hold marker unreadable: {exc}`, and an OSError's text carries the marker's full path
(`[Errno 13] Permission denied: '<server path>'`), so an unauthenticated read leaked the data directory layout. The `ledger busy:`
prefix other services key on stays. `/retention/check` is not touched (test_filters_retention_direct_c1205.py pins its detail)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ledger_c2_support import three_segments
from sealed_ledger.api import create_app

PREFIX = "ledger busy: hold marker unreadable"


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    s, p, _ = three_segments(tmp_path / "data" / "ledger")
    return s, TestClient(create_app(store=s, registry=None))


def test_a_permission_error_is_a_503_without_the_path(stack, tmp_path, monkeypatch):
    s, client = stack
    secret = str(tmp_path / "data" / "ledger" / "legal_hold.json")

    def boom():
        raise PermissionError(13, "Permission denied", secret)
    monkeypatch.setattr(s, "hold_status", boom)
    r = client.get("/hold")
    assert r.status_code == 503
    assert r.json()["detail"] == f"{PREFIX} (PermissionError)"
    assert secret not in r.text and str(tmp_path) not in r.text and "Errno" not in r.text and "Permission denied" not in r.text


@pytest.mark.parametrize("exc", [OSError("disk gone /srv/secret/hold"), FileNotFoundError(2, "No such file", "/srv/secret/hold"),
                                 IsADirectoryError(21, "Is a directory", "/srv/secret/hold")], ids=lambda e: type(e).__name__)
def test_every_oserror_names_only_its_class(stack, monkeypatch, exc):
    s, client = stack

    def boom():
        raise exc
    monkeypatch.setattr(s, "hold_status", boom)
    r = client.get("/hold")
    assert r.status_code == 503
    assert r.json()["detail"] == f"{PREFIX} ({type(exc).__name__})"
    assert "/srv/secret" not in r.text


def test_a_real_unreadable_marker_does_not_leak_the_path(stack, tmp_path):
    """No monkeypatch: the marker path is a directory, so the real read raises."""
    s, client = stack
    s.hold_path.mkdir(parents=True)
    r = client.get("/hold")
    assert r.status_code == 503, r.text
    assert r.json()["detail"].startswith(PREFIX + " (")
    assert str(tmp_path) not in r.text and s.hold_path.name not in r.text


def test_the_prefix_other_services_key_on_is_kept(stack, monkeypatch):
    s, client = stack
    monkeypatch.setattr(s, "hold_status", lambda: (_ for _ in ()).throw(OSError("x")))
    assert client.get("/hold").json()["detail"].startswith("ledger busy:")


def test_the_readable_paths_are_unchanged(stack):
    s, client = stack
    assert client.get("/hold").json() == {"held": False, "hold": None}
    assert client.post("/hold", json={"by": "counsel", "reason": "litigation"}).status_code == 201
    got = client.get("/hold").json()
    assert got["held"] is True and got["hold"]["reason"] == "litigation"
