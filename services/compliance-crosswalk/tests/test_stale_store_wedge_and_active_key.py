"""B-REGWATCH-SURROGATE-WEDGE and B-REGWATCH-ACTIVE-KEY: the stale-flags store.

SURROGATE: a lone-surrogate escape (JSON ``\\ud800``) in any stored record loads fine, and then every ``_persist``
raised ``UnicodeEncodeError`` at the UTF-8 write, so a regwatch check never recorded a new source change and
``set-stale`` failed: stale detection was dead until someone hand-edited the file. The fix writes such a store as
ASCII-escaped JSON (still valid UTF-8 JSON, round-trips, nothing is dropped or replaced).

ACTIVE-KEY: ``json.loads`` keeps the LAST of a duplicate key, and ``dict(data.get("active"))`` swallowed some wrong
types, so a duplicate top-level ``"active"`` or an ``"active": []`` read as "no flags" and the evidence pack was
generated while a flag stood. The loader now refuses a duplicate key anywhere and a wrong top-level type with
``StaleStoreError`` (a fixed message: the file's name and what is wrong, never its text), the pack is refused, and the
file is never rewritten, so the standing flag stays until a NAMED human clears it. Every value is made up."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import regwatch, staleness
from compliance_crosswalk.api import create_app
from compliance_crosswalk.cli import app as cli_app
from compliance_crosswalk.evidence_pack import generate_pack
from compliance_crosswalk.mapping import SRC_NIST, SRC_OSFI
from compliance_crosswalk.staleness import StaleStore
from test_pack_api import resolved_manifest
from test_regwatch import FakeFetcher, by_framework, page

MARK = "MARKER-5b1e"
SIGNER = "Controller, Spin State Labs"
FLAG = {"framework": "osfi-e23", "flagged_at": "2026-11-01T00:00:00+00:00", "reason": "r", "new_version": None}
SURROGATE = "\\ud800"                    # the JSON escape of a lone high surrogate


@pytest.fixture()
def path(tmp_path):
    return tmp_path / "crosswalk_stale_flags.json"


def raw(path, content):
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def standing(path):
    """A real store holding one flag, written by the store itself."""
    StaleStore(path).mark("osfi-e23", "standing")
    return path


def error_type():
    return staleness.StaleStoreError


def pack_of(store):
    return generate_pack(resolved_manifest(), signer=SIGNER, stale_store=store)


# --- SURROGATE: _persist survives any str -------------------------------------------------------------------------------
def poisoned(path):
    """Baseline once, then put a lone-surrogate escape into one stored source record (as a hand edit, an older
    version or a hostile fetch error text would)."""
    regwatch.run_check(StaleStore(path), FakeFetcher())
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    data["sources"][SRC_OSFI]["via"] = "x" + chr(0xD800) + "y"
    path.write_bytes(json.dumps(data, ensure_ascii=True).encode("ascii"))
    assert SURROGATE in path.read_text(encoding="ascii")
    return path


def test_a_stored_lone_surrogate_does_not_stop_a_new_source_change_being_flagged(path):
    poisoned(path)
    changed = FakeFetcher({SRC_NIST: page(text="Amended text, entirely different now.")})
    report = regwatch.run_check(StaleStore(path), changed)             # raised UnicodeEncodeError in _persist
    assert by_framework(report)["nist-ai-rmf"]["status"] == "changed"
    assert report["flagged"] == ["nist-ai-rmf"]
    assert [f["framework"] for f in StaleStore(path).active()] == ["nist-ai-rmf"]


def test_set_stale_still_works_after_a_stored_lone_surrogate(path):
    poisoned(path)
    flag = StaleStore(path).mark("osfi-e23", "amended")                  # raised UnicodeEncodeError in _persist
    assert flag["framework"] == "osfi-e23"
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]


def test_the_file_stays_valid_utf8_json_and_the_surrogate_round_trips(path):
    poisoned(path)
    StaleStore(path).mark("osfi-e23", "amended")
    data = json.loads(path.read_bytes().decode("utf-8"))                 # strict UTF-8 decode, then JSON
    assert data["sources"][SRC_OSFI]["via"] == "x" + chr(0xD800) + "y"   # nothing dropped, nothing replaced
    assert StaleStore(path).source_record(SRC_OSFI)["via"] == "x" + chr(0xD800) + "y"


def test_a_surrogate_in_the_reason_is_stored_not_a_traceback(path):
    StaleStore(path).mark("osfi-e23", "bad " + chr(0xDC00) + " reason")
    assert StaleStore(path).active()[0]["reason"] == "bad " + chr(0xDC00) + " reason"
    path.read_bytes().decode("utf-8")


def test_ordinary_text_is_still_written_readably(path):
    StaleStore(path).mark("osfi-e23", "révision — 規則")
    assert "révision — 規則" in path.read_text(encoding="utf-8")         # the common case is unchanged


def test_the_cli_set_stale_works_after_a_stored_lone_surrogate(path, monkeypatch):
    poisoned(path)
    monkeypatch.setenv("FIELD_DATA_DIR", str(path.parent))
    res = CliRunner().invoke(cli_app, ["regwatch", "set-stale", "osfi-e23", "--reason", "amended"])
    assert res.exit_code == 0, res.output
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]


# --- ACTIVE-KEY: a standing flag is never silently dropped --------------------------------------------------------------
DUP_ACTIVE = ('{"corpus_version": "x", "active": {"osfi-e23": ' + json.dumps(FLAG) + '}, "history": [], '
              '"sources": {}, "last_check": null, "active": {}}')
DUP_ACTIVE_EMPTY_FIRST = '{"active": {}, "active": {"osfi-e23": ' + json.dumps(FLAG) + '}}'
ACTIVE_EMPTY_LIST = '{"corpus_version": "x", "active": [], "history": [], "sources": {}, "last_check": null}'

REFUSED = {
    "duplicate-active-last-wins": DUP_ACTIVE,
    "duplicate-active-first-empty": DUP_ACTIVE_EMPTY_FIRST,
    "active-empty-list": ACTIVE_EMPTY_LIST,
    "active-list-with-flag": json.dumps({"active": [FLAG]}),
    "active-null": json.dumps({"active": None}),
    "active-string": json.dumps({"active": MARK}),
    "active-value-not-object": json.dumps({"active": {"osfi-e23": MARK}}),
    "duplicate-inside-a-flag": '{"active": {"osfi-e23": {"framework": "osfi-e23", "framework": "nist-ai-rmf"}}}',
    "duplicate-history": '{"history": [], "history": []}',
    "duplicate-sources-url": '{"sources": {"u": {"a": 1}, "u": {"a": 2}}}',
    "history-object": json.dumps({"history": {"k": MARK}}),
    "sources-list": json.dumps({"sources": [MARK]}),
    "last-check-list": json.dumps({"last_check": [MARK]}),
    "top-list": json.dumps([MARK]),
    "top-null": "null",
    "not-json": MARK,
    "truncated": '{"active": {"osfi-e23": ' + MARK,
    "empty-file": "",
    "not-utf8": b"\xff\xfe" + MARK.encode(),
}


@pytest.mark.parametrize("name", list(REFUSED))
def test_a_duplicate_key_or_wrong_type_is_a_named_refusal_that_never_echoes_the_file(path, name):
    raw(path, REFUSED[name])
    with pytest.raises(error_type()) as exc:
        StaleStore(path)
    text = str(exc.value)
    assert path.name in text and "evidence-pack generation stays blocked" in text
    assert MARK not in text and str(path.parent) not in text and "osfi-e23" not in text
    assert not any(w in text for w in ("codec", "Expecting", "line 1", "column", "byte "))   # no exception text either
    assert exc.value.__cause__ is None and (exc.value.__context__ is None or exc.value.__suppress_context__)


@pytest.mark.parametrize("name", ["duplicate-active-last-wins", "duplicate-active-first-empty", "active-empty-list"])
def test_the_evidence_pack_is_refused_while_the_flag_stands_in_a_refused_file(path, name):
    raw(path, REFUSED[name])
    with pytest.raises(error_type()):
        pack_of(StaleStore(path))                 # on main: a pack was generated, the flag silently dropped


def test_a_good_store_with_a_standing_flag_still_blocks_the_pack(path):
    standing(path)
    with pytest.raises(Exception) as exc:
        pack_of(StaleStore(path))
    assert type(exc.value).__name__ == "StalePackError"


def test_a_good_empty_or_missing_store_still_generates_the_pack(path):
    md, payload = pack_of(StaleStore(path))        # no file: never written, an empty store
    assert md and payload["manifest_valid"] is True
    StaleStore(path).mark("osfi-e23", "r")
    StaleStore(path).clear("osfi-e23", "Ann Reviewer")
    assert pack_of(StaleStore(path))[0]


@pytest.mark.parametrize("name", ["duplicate-active-last-wins", "active-empty-list", "truncated"])
def test_no_write_path_rewrites_a_refused_file_so_the_flag_is_kept(path, name):
    raw(path, REFUSED[name])
    before = path.read_bytes()
    with pytest.raises(error_type()):
        StaleStore(path).mark("nist-ai-rmf", "r")
    with pytest.raises(error_type()):
        StaleStore(path).clear("osfi-e23", "Ann Reviewer")           # a clear on a damaged file is refused too
    with pytest.raises(error_type()):
        regwatch.run_check(StaleStore(path), FakeFetcher())
    assert path.read_bytes() == before and not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("name", ["duplicate-active-last-wins", "active-empty-list", "truncated"])
def test_a_file_damaged_after_the_store_was_built_is_refused_at_write_time_and_not_overwritten(path, name):
    """The write paths re-load under the lock: a store built on a good file, whose file is then damaged, must refuse
    (and must not persist its in-memory state over the damaged file, which would drop the flag it holds)."""
    standing(path)
    store = StaleStore(path)
    raw(path, REFUSED[name])
    before = path.read_bytes()
    with pytest.raises(error_type()):
        store.mark("nist-ai-rmf", "r")
    with pytest.raises(error_type()):
        store.clear("osfi-e23", "Ann Reviewer")
    with pytest.raises(error_type()):
        regwatch.run_check(store, FakeFetcher())
    assert path.read_bytes() == before and not list(path.parent.glob("*.tmp"))


def test_generate_pack_lets_a_store_refusal_through(path):
    class Refusing:
        def active(self):
            raise staleness.StaleStoreError("fixed")

        def status(self):
            return {"corpus_version": staleness.CORPUS_VERSION, "active": []}

    with pytest.raises(error_type()):
        pack_of(Refusing())


def test_the_flag_comes_back_only_through_the_named_human_path(path):
    """After the operator repairs the file, the flag stands again and only a named clear removes it."""
    raw(path, DUP_ACTIVE)
    with pytest.raises(error_type()):
        StaleStore(path)
    raw(path, json.dumps({"active": {"osfi-e23": FLAG}}))            # repaired by hand: one active key
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]
    with pytest.raises(ValueError):
        StaleStore(path).clear("osfi-e23", "   ")                    # not named: refused, flag stays
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]
    StaleStore(path).clear("osfi-e23", "Ann Reviewer")
    assert StaleStore(path).active() == []


def test_a_file_without_the_optional_keys_loads_as_before(path):
    raw(path, json.dumps({"corpus_version": "x"}))
    store = StaleStore(path)
    assert store.active() == [] and store.last_check() is None and store.sources() == {}


def test_a_valid_store_round_trips_unchanged(path):
    regwatch.run_check(StaleStore(path), FakeFetcher())
    StaleStore(path).mark("osfi-e23", "r")
    assert StaleStore(path).last_check() is not None and len(StaleStore(path).sources()) == 3


# --- HTTP and CLI: a fixed refusal, the pack is not generated -------------------------------------------------------------
@pytest.mark.parametrize("name", ["duplicate-active-last-wins", "active-empty-list"])
def test_http_refuses_with_a_fixed_503_and_generates_no_pack(path, monkeypatch, name):
    raw(path, REFUSED[name])
    monkeypatch.setenv("FIELD_DATA_DIR", str(path.parent))
    client = TestClient(create_app(), raise_server_exceptions=False)
    for method, route, body in (("post", "/pack", {"signer": SIGNER, "manifest": resolved_manifest()}),
                                ("get", "/staleness", None), ("post", "/regwatch/check", None)):
        r = getattr(client, method)(route, **({"json": body} if body is not None else {}))
        assert r.status_code == 503, (route, r.status_code, r.text)
        assert "damaged" in r.json()["detail"] and "markdown" not in r.text and "pack" not in r.json()
        assert MARK not in r.text and str(path.parent) not in r.text and "osfi-e23" not in r.text


@pytest.mark.parametrize("name", ["duplicate-active-last-wins", "active-empty-list"])
def test_cli_refuses_with_one_fixed_line_and_exit_2(path, monkeypatch, name):
    raw(path, REFUSED[name])
    before = path.read_bytes()
    monkeypatch.setenv("FIELD_DATA_DIR", str(path.parent))
    manifest = path.parent / "m.yaml"
    import yaml

    manifest.write_text(yaml.safe_dump(resolved_manifest(), sort_keys=False), encoding="utf-8")
    for args in (["regwatch", "status"], ["regwatch", "set-stale", "osfi-e23", "--reason", "r"],
                 ["regwatch", "clear", "osfi-e23", "--reviewed-by", "Ann Reviewer"], ["regwatch", "check"],
                 ["pack", str(manifest), "--signer", SIGNER]):
        res = CliRunner().invoke(cli_app, args)
        assert res.exit_code == 2, (args, res.exit_code, res.output)
        out = (res.output or "").strip()
        assert out.startswith("error: the stale-flags store crosswalk_stale_flags.json is damaged"), (args, out)
        assert len(out.splitlines()) == 1 and "Traceback" not in out and MARK not in out
        assert res.exception is None or isinstance(res.exception, SystemExit)
    assert path.read_bytes() == before
