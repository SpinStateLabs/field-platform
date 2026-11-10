"""S10-25: a damaged stale-flags file fails CLOSED with a named ``StaleStoreError``, never as an anonymous traceback and never
as an empty store (an empty store would reopen the evidence-pack gate that a stale flag closes).

Store: bytes that are not UTF-8, truncated or non-JSON text, a top level that is not an object, ``active`` not an object of
objects, ``history`` not a list, ``sources`` not an object, ``last_check`` neither null nor an object, an unreadable path,
and a flag whose ``flagged_at`` is missing, unparseable, naive or not text, or that has no ``framework``. The message names the
file (its name) and the exception type, never the file's text. HTTP: 503 on GET /staleness, POST /regwatch/check and POST /pack
(nothing generated). CLI: one ``error:`` line and exit 2 for status, set-stale, clear, check, check-file and pack. A missing file
is still an empty store; a valid one is unchanged; mark and clear never overwrite a damaged file. Every value is made up."""
from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import cli as cli_module
from compliance_crosswalk.api import create_app
from compliance_crosswalk.staleness import StaleStore, StaleStoreError
from field_core.templates_api import template_data

MARK = "MARKER-7a52"
GOOD_FLAG = {"framework": "osfi-e23", "reason": "r", "flagged_at": "2026-11-01T00:00:00+00:00"}

DAMAGED = {
    "not-utf8": b"\xff\xfe\x00" + MARK.encode(),
    "truncated": b'{"active": {"osfi-e23": ' + MARK.encode(),
    "not-json": MARK.encode(),
    "empty-file": b"",
    "top-list": json.dumps([MARK]).encode(),
    "top-string": json.dumps(MARK).encode(),
    "top-null": b"null",
    "active-list": json.dumps({"active": [MARK]}).encode(),
    "active-value-not-object": json.dumps({"active": {"osfi-e23": MARK}}).encode(),
    "history-object": json.dumps({"history": {"k": MARK}}).encode(),
    "history-string": json.dumps({"history": MARK}).encode(),
    "sources-list": json.dumps({"sources": [MARK]}).encode(),
    "last-check-list": json.dumps({"last_check": [MARK]}).encode(),
    "last-check-string": json.dumps({"last_check": MARK}).encode(),
    "last-check-int": json.dumps({"last_check": 7}).encode(),
}


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return tmp_path


def write(data_dir, content: bytes):
    path = data_dir / "crosswalk_stale_flags.json"
    path.write_bytes(content)
    return path


# -- the store ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(DAMAGED))
def test_a_damaged_file_is_a_named_error_that_never_carries_its_text(data_dir, name):
    path = write(data_dir, DAMAGED[name])
    with pytest.raises(StaleStoreError) as exc:
        StaleStore(path)
    text = str(exc.value)
    assert path.name in text and "damaged" in text and "blocked" in text
    assert MARK not in text and str(data_dir) not in text
    assert exc.value.__cause__ is None


def test_the_error_names_the_exception_type_for_the_read_and_decode_failures(data_dir):
    with pytest.raises(StaleStoreError, match="UnicodeDecodeError"):
        StaleStore(write(data_dir, b"\xff\xfe"))
    with pytest.raises(StaleStoreError, match="JSONDecodeError"):
        StaleStore(write(data_dir, b'{"a": '))
    directory = data_dir / "is-a-dir.json"
    directory.mkdir()
    with pytest.raises(StaleStoreError, match="IsADirectoryError|PermissionError"):
        StaleStore(directory)


def test_a_missing_file_is_still_an_empty_store_and_a_valid_one_loads(data_dir):
    assert StaleStore(data_dir / "absent.json").status()["active"] == []
    store = StaleStore(data_dir / "ok.json")
    store.mark("osfi-e23", "new amendment")
    again = StaleStore(data_dir / "ok.json")
    assert [f["framework"] for f in again.status()["active"]] == ["osfi-e23"]


def test_a_file_without_the_optional_keys_loads_as_before(data_dir):
    path = write(data_dir, json.dumps({"corpus_version": "x"}).encode())
    status = StaleStore(path).status()
    assert status["active"] == [] and status["history"] == [] and status["last_check"] is None


@pytest.mark.parametrize("flag", [
    {"framework": "osfi-e23", "reason": "r"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": "not-a-date"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": "2026-11-01T00:00:00"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": 12345},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": None},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": [MARK]},
], ids=["missing", "unparseable", "naive", "int", "null", "list"])
def test_a_flag_with_a_bad_flagged_at_is_a_named_error_from_status(data_dir, flag):
    store = StaleStore(write(data_dir, json.dumps({"active": {"osfi-e23": flag}}).encode()))
    with pytest.raises(StaleStoreError, match="flagged_at") as exc:
        store.status()
    assert MARK not in str(exc.value)


def test_a_flag_without_a_framework_is_a_named_error(data_dir):
    store = StaleStore(write(data_dir, json.dumps({"active": {"x": {"flagged_at": GOOD_FLAG["flagged_at"]}}}).encode()))
    with pytest.raises(StaleStoreError, match="framework"):
        store.status()


def test_a_good_flag_reports_its_window(data_dir):
    store = StaleStore(write(data_dir, json.dumps({"active": {"osfi-e23": GOOD_FLAG}}).encode()))
    (flag,) = store.status()["active"]
    assert flag["stale_window_seconds"] > 0


@pytest.mark.parametrize("name", ["truncated", "active-list", "top-list"])
def test_mark_and_clear_refuse_and_never_overwrite_a_damaged_file(data_dir, name):
    path = write(data_dir, DAMAGED[name])
    before = path.read_bytes()
    for action in (lambda s: s.mark("osfi-e23", "r"), lambda s: s.clear("osfi-e23", "Ann")):
        with pytest.raises(StaleStoreError):
            action(StaleStore(path))
    assert path.read_bytes() == before            # the evidence of the damage is intact; nothing was written over it
    assert not list(data_dir.glob("*.tmp"))


# -- HTTP --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["truncated", "active-list", "top-list", "not-utf8"])
def test_http_routes_answer_503_with_the_named_text_and_pack_stays_blocked(data_dir, name):
    write(data_dir, DAMAGED[name])
    client = TestClient(create_app(), raise_server_exceptions=False)
    for method, path, body in (("get", "/staleness", None), ("post", "/regwatch/check", None),
                               ("post", "/pack", {"signer": "Ann", "manifest": {}})):
        r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 503, (path, r.status_code, r.text)
        detail = r.json()["detail"]
        assert "crosswalk_stale_flags.json" in detail and "damaged" in detail
        assert MARK not in r.text and str(data_dir) not in r.text
        assert "markdown" not in r.text and "pack" not in r.json()


def test_http_still_serves_an_empty_and_a_valid_store(data_dir):
    client = TestClient(create_app())
    assert client.get("/staleness").status_code == 200           # no file at all
    write(data_dir, json.dumps({"active": {"osfi-e23": GOOD_FLAG}}).encode())
    assert [f["framework"] for f in client.get("/staleness").json()["active"]] == ["osfi-e23"]


# -- CLI ---------------------------------------------------------------------------------------------------------------
runner = CliRunner()


def manifest_file(tmp_path):
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(template_data("default"), sort_keys=False), encoding="utf-8")
    return p


def page(tmp_path):
    p = tmp_path / "page.html"
    p.write_text("<html><body>PIPEDA text</body></html>", encoding="utf-8")
    return p


def cli_cases(tmp_path):
    return {
        "status": ["regwatch", "status"],
        "set-stale": ["regwatch", "set-stale", "osfi-e23", "--reason", "r"],
        "clear": ["regwatch", "clear", "osfi-e23", "--reviewed-by", "Ann"],
        "check-inventory": ["regwatch", "check"],
        "check-fetch": ["regwatch", "check", "--fetch"],
        "check-file": ["regwatch", "check-file", "osfi-e23", "--file", str(page(tmp_path)), "--fetched-by", "Ann"],
        "pack": ["pack", str(manifest_file(tmp_path)), "--signer", "Ann"],
    }


@pytest.mark.parametrize("verb", ["status", "set-stale", "clear", "check-inventory", "check-fetch", "check-file", "pack"])
@pytest.mark.parametrize("name", ["truncated", "active-list"])
def test_every_cli_verb_is_one_error_line_and_exit_2_on_a_damaged_store(data_dir, verb, name):
    path = write(data_dir, DAMAGED[name])
    before = path.read_bytes()
    res = runner.invoke(cli_module.app, cli_cases(data_dir)[verb])
    assert res.exit_code == 2, (verb, res.exit_code, res.output)
    assert res.output.strip().startswith("error: the stale-flags store crosswalk_stale_flags.json is damaged")
    assert len(res.output.strip().splitlines()) == 1
    assert "Traceback" not in res.output and MARK not in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)
    assert path.read_bytes() == before


def test_the_cli_still_works_on_a_valid_store(data_dir):
    res = runner.invoke(cli_module.app, ["regwatch", "set-stale", "osfi-e23", "--reason", "r"])
    assert res.exit_code == 0 and "stale: osfi-e23" in res.output
    res = runner.invoke(cli_module.app, ["regwatch", "status"])
    assert res.exit_code == 0 and json.loads(res.output)["active"][0]["framework"] == "osfi-e23"
