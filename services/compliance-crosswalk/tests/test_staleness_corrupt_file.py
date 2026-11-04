"""Scout S-2-24: `StaleStore._load` did `json.loads` and `dict()`/`list()` on the flags file's members with no guard.
Invalid JSON raised JSONDecodeError, a top-level list or null raised AttributeError, `active` as a list raised
ValueError, and the API answered 500 (`POST /pack` built `StaleStore()` outside its try). The rule that matters is that a
corrupt file must NEVER read as an empty store: an empty store unblocks evidence packs while a stale regulatory flag
stands. So `_load` raises `StoreCorrupt` (the class name and the file's basename, never its content); the API answers 503
with a fixed text; the CLI prints one line and exits 2; the scheduler survives and logs. A missing file is still an empty
store, and a file written before D4 (no `sources`, no `last_check`) still loads. The on-disk format and the lock code are
unchanged."""
from __future__ import annotations

import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import regwatch
from compliance_crosswalk.api import create_app
from compliance_crosswalk.cli import app as cli_app
from compliance_crosswalk.mapping import FRAMEWORKS
from compliance_crosswalk.staleness import StaleStore, StoreCorrupt
from field_core.templates_api import template_data

FW = sorted(FRAMEWORKS)[0]
MARK = "FILE-CONTENT-MARKER-5512"
NAME = "crosswalk_stale_flags.json"
FLAG = {"framework": FW, "flagged_at": "2026-01-01T00:00:00+00:00", "reason": "r", "new_version": None}

CORRUPT = {
    "truncated-json": b'{"active": {"x": {"fra',
    "empty-file": b"",
    "whitespace": b"   \n",
    "not-json": b"this is not json " + MARK.encode(),
    "list": b"[]",
    "list-of-flags": json.dumps([FLAG]).encode(),
    "null": b"null",
    "number": b"5",
    "string": b'"' + MARK.encode() + b'"',
    "active-list": b'{"active": []}',
    "active-null": b'{"active": null}',
    "active-string": b'{"active": "x"}',
    "active-member-not-object": json.dumps({"active": {FW: "not a flag"}}).encode(),
    "active-member-list": json.dumps({"active": {FW: [1]}}).encode(),
    "history-object": b'{"history": {}}',
    "history-string": b'{"history": "x"}',
    "sources-list": b'{"sources": []}',
    "sources-member-not-object": b'{"sources": {"u": 5}}',
    "last-check-number": b'{"last_check": 5}',
    "last-check-list": b'{"last_check": []}',
    "not-utf8": b"\xff\xfe\x00{" + MARK.encode(),
}


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    return tmp_path


def corrupt(tmp_path, kind):
    (tmp_path / NAME).write_bytes(CORRUPT[kind])
    return tmp_path / NAME


# ---- the store -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(CORRUPT))
def test_a_corrupt_or_wrong_shaped_file_raises_store_corrupt_and_never_reads_as_empty(tmp_path, kind):
    path = corrupt(tmp_path, kind)
    with pytest.raises(StoreCorrupt) as e:
        StaleStore(path)
    msg = str(e.value)
    assert NAME in msg and MARK not in msg and str(tmp_path) not in msg
    assert any(c in msg for c in ("Error", "Corrupt", "Shape")), msg      # a class name


def test_the_error_names_the_failure_class_and_the_basename_only(tmp_path):
    msg = str(pytest.raises(StoreCorrupt, StaleStore, corrupt(tmp_path, "truncated-json")).value)
    assert "JSONDecodeError" in msg and NAME in msg and "/" not in msg


def test_a_directory_where_the_file_should_be_is_corrupt_not_empty(tmp_path):
    (tmp_path / NAME).mkdir()
    with pytest.raises(StoreCorrupt):
        StaleStore(tmp_path / NAME)


def test_a_missing_file_is_still_an_empty_store(tmp_path):
    s = StaleStore(tmp_path / NAME)
    assert s.active() == [] and s.status()["last_check"] is None


@pytest.mark.parametrize("body", [
    {},                                                                   # nothing but defaults
    {"corpus_version": "x", "active": {}, "history": []},                 # written before D4: no sources, no last_check
    {"corpus_version": "x", "active": {FW: FLAG}, "history": [{"framework": FW, "reviewed_by": "A"}]},
    {"active": {}, "history": [], "sources": {"https://u.example": {"sha256": "ab"}}, "last_check": {"at": "t"}},
    {"active": {}, "history": [], "sources": {}, "last_check": None},
])
def test_a_well_formed_file_including_a_pre_d4_one_still_loads(tmp_path, body):
    (tmp_path / NAME).write_text(json.dumps(body), encoding="utf-8")
    StaleStore(tmp_path / NAME)


def test_a_pre_d4_file_with_a_flag_loads_with_that_flag(tmp_path):
    (tmp_path / NAME).write_text(json.dumps({"corpus_version": "x", "active": {FW: FLAG}, "history": []}),
                                 encoding="utf-8")
    assert [f["framework"] for f in StaleStore(tmp_path / NAME).active()] == [FW]


def test_a_corrupt_file_is_left_untouched_by_the_failed_load(tmp_path):
    path = corrupt(tmp_path, "list-of-flags")
    before = path.read_bytes()
    with pytest.raises(StoreCorrupt):
        StaleStore(path)
    assert path.read_bytes() == before


def test_a_transaction_on_a_corrupt_file_raises_and_does_not_overwrite_it(tmp_path):
    good = StaleStore(tmp_path / NAME)
    good.mark(FW, "r")
    path = tmp_path / NAME
    path.write_bytes(b"[]")                                                # corrupted after this instance loaded
    with pytest.raises(StoreCorrupt):
        good.mark(FW, "again")
    assert path.read_bytes() == b"[]"


# ---- the API: 503 with a fixed text ----------------------------------------------------------------------------------

def pack_body():
    return {"signer": "A. Signer", "manifest": template_data("default")}


@pytest.fixture()
def api(data_dir):
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("kind", ["truncated-json", "list", "null", "active-list", "not-json", "not-utf8"])
@pytest.mark.parametrize("call", [
    lambda c: c.get("/staleness"),
    lambda c: c.post("/regwatch/check"),
    lambda c: c.post("/pack", json=pack_body()),
], ids=["staleness", "regwatch-check", "pack"])
def test_the_api_answers_503_with_a_fixed_text_for_a_corrupt_file(api, data_dir, kind, call):
    corrupt(data_dir, kind)
    r = call(api)
    assert r.status_code == 503, (r.status_code, r.text)
    assert MARK not in r.text and "Traceback" not in r.text and str(data_dir) not in r.text
    assert "stale" in r.json()["detail"].lower()


def test_pack_is_503_not_200_when_the_file_is_corrupt_while_a_flag_existed(api, data_dir):
    s = StaleStore(data_dir / NAME)
    s.mark(FW, "RMF 2.0")
    blocked = api.post("/pack", json=pack_body())
    assert blocked.status_code == 409                                      # the flag blocks, as before
    (data_dir / NAME).write_bytes(b'{"active": {"os')                      # now the file is damaged
    r = api.post("/pack", json=pack_body())
    assert r.status_code == 503 and "markdown" not in r.text               # never an empty store that unblocks


def test_the_api_still_works_on_a_good_or_missing_file(api, data_dir):
    assert api.get("/staleness").status_code == 200
    StaleStore(data_dir / NAME).mark(FW, "r")
    assert api.get("/staleness").json()["active"][0]["framework"] == FW


# ---- the CLI: one line, exit 2 ---------------------------------------------------------------------------------------

runner = CliRunner()


@pytest.mark.parametrize("args", [
    ["regwatch", "status"],
    ["regwatch", "check"],
    ["regwatch", "set-stale", FW, "--reason", "r"],
    ["regwatch", "clear", FW, "--reviewed-by", "A. Reviewer"],
], ids=lambda a: a[1])
@pytest.mark.parametrize("kind", ["truncated-json", "list", "active-list"])
def test_the_cli_prints_one_line_and_exits_2_on_a_corrupt_file(data_dir, args, kind):
    path = corrupt(data_dir, kind)
    before = path.read_bytes()
    r = runner.invoke(cli_app, args)
    assert r.exit_code == 2, (r.exit_code, r.output)
    assert "Traceback" not in r.output and r.exception is None or isinstance(r.exception, SystemExit)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0].startswith("error:") and NAME in lines[0]
    assert path.read_bytes() == before


# ---- the scheduler survives ----------------------------------------------------------------------------------------------

def test_a_scheduled_check_on_a_corrupt_file_returns_none_and_logs_the_class(data_dir, caplog):
    corrupt(data_dir, "list")
    with caplog.at_level(logging.ERROR):
        assert regwatch.scheduled_check(StaleStore) is None
    assert "StoreCorrupt" in caplog.text and MARK not in caplog.text


def test_the_loop_keeps_ticking_through_a_corrupt_file(data_dir):
    corrupt(data_dir, "truncated-json")
    stop = threading.Event()
    seen = []

    def tick():
        seen.append(regwatch.scheduled_check(StaleStore))
        if len(seen) == 3:
            stop.set()

    assert regwatch.run_every(tick, 5, stop, sleep=lambda s: None) == 3
    assert seen == [None, None, None]
