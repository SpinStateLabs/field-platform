"""S7-25 — POST /export: a bad out_dir is a fixed 422 (armed and unarmed), a directory that cannot
be written is a 500 whose body has no server path, and a ValueError from the run is a fixed 500."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import MAX_OUT_DIR, create_app
from sealed_ledger.store import LedgerStore

KEY = "fok_don-key-0123456789abcdef"
H = {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY}
BAD = ["a\x00b", "x" * (MAX_OUT_DIR + 1)]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_EXPORT_ROOT"):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def store(tmp_path):
    s = LedgerStore(tmp_path / "ledger" / "e.jsonl")
    s.append("x.event", {"i": 1})
    return s


@pytest.fixture(params=["unarmed", "armed"])
def ctx(request, store, tmp_path, monkeypatch):
    headers = {}
    if request.param == "armed":
        p = tmp_path / "operators.json"
        p.write_text(json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(KEY),
                                  "status": "active", "scopes": ["*"]}]), encoding="utf-8")
        monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
        monkeypatch.setenv("FIELD_EXPORT_ROOT", str(tmp_path / "root"))
        headers = H
    return TestClient(create_app(store=store), raise_server_exceptions=False), headers


@pytest.mark.parametrize("out_dir", BAD, ids=["nul", "too-long"])
def test_a_bad_out_dir_is_422_with_fixed_text(ctx, out_dir):
    client, h = ctx
    r = client.post("/export", params={"out_dir": out_dir}, headers=h)
    assert r.status_code == 422, r.text
    assert "out_dir must be a path" in r.json()["detail"]
    assert len(r.text) < 400  # the value is not echoed


def test_a_lone_surrogate_is_refused_by_the_helper():
    """HTTP cannot carry one (a query is decoded with replacement), so the guard is tested directly."""
    from sealed_ledger.api import _bad_out_dir

    assert _bad_out_dir("a\udcffb") and not _bad_out_dir("a\u00e9b")


def test_the_longest_allowed_out_dir_is_not_refused_by_the_bound(ctx):
    client, h = ctx
    r = client.post("/export", params={"out_dir": "y" * MAX_OUT_DIR}, headers=h)
    assert r.status_code != 422 or "out_dir must be a path" not in r.json().get("detail", "")


def test_an_unwritable_out_dir_is_500_with_no_path_in_the_body(ctx, tmp_path, caplog):
    client, h = ctx
    blocker = tmp_path / "root" / "afile" if h else tmp_path / "afile"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("x")
    target = "afile/sub" if h else str(blocker / "sub")
    with caplog.at_level(logging.WARNING, logger="sealed_ledger.api"):
        r = client.post("/export", params={"out_dir": target}, headers=h)
    assert r.status_code == 500, r.text
    assert r.json()["detail"] == "export directory could not be written"
    assert str(tmp_path) not in r.text and "Errno" not in r.text
    assert "export failed:" in caplog.text and str(tmp_path) not in caplog.text


def test_a_value_error_from_the_run_is_a_fixed_500(ctx, store, monkeypatch):
    client, h = ctx

    def boom(*a, **k):
        raise ValueError("SECRET-STORED-TS-VALUE")

    monkeypatch.setattr(type(store), "export", boom)
    r = client.post("/export", params={"out_dir": "ok"} if h else None, headers=h)
    assert r.status_code == 500, r.text
    assert "SECRET-STORED-TS-VALUE" not in r.text
    assert r.json()["detail"] == "export failed: a stored event could not be read"


def test_existing_paths_are_unchanged(ctx, tmp_path):
    client, h = ctx
    assert client.post("/export", params={"since": "not-a-date"}, headers=h).status_code == 422
    ok = client.post("/export", params={"out_dir": "sub"} if h else {"out_dir": str(tmp_path / "sub")}, headers=h)
    assert ok.status_code == 200, ok.text
    if h:
        assert client.post("/export", params={"out_dir": "../../etc"}, headers=h).status_code == 422
