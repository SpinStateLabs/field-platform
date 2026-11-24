"""B87 round 1: the routes the first change did not cover, plus the places that print file content on stdout.

* the DEFAULT route: ``ledger verify --path ledger.jsonl`` opens the store (a strict snapshot) and used to raise the
  parser's exception, a traceback that carried pydantic's multi-line message; now one ``TAMPERED`` line, exit 1;
* the live CLOSED-segment route (``<stem>-<n>.jsonl`` beside its journal): the same, and a nested line;
* ``--event-pubkey`` / ``--caller-keyring``: the SIGNATURE INVALID / CALLER UNKNOWN lines print ``event_id`` and
  ``event_type``, both free text, on stdout;
* the lines the first change already routed through ``_one_line`` and no test pinned: ANCHOR FAILURE, EXPORT FAILED,
  the closed-segment and main-route TAMPERED sites, and the ``archived_to`` text of an exit-0 line.

All inputs are file CONTENT, so none of these tests needs a POSIX-only file system."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from field_core.ledger import compute_event_hash
from field_core.signing import generate_keypair
from sealed_ledger import store as store_mod
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore, closed_path_for
from ledger_c2_support import three_segments

runner = CliRunner()

PHRASE = "(signed rotation anchor verified: it pins this segment's head and chain_length)"
FORGED_OK = "OK — chain intact over 999 events"
ESC = chr(27)


def _plain(tmp_path, n=6):
    path = tmp_path / "plain" / "events.jsonl"
    path.parent.mkdir()
    store = LedgerStore(path)
    for i in range(n):
        store.append("action", {"seq": i}, agent_id="rt-agent")
    assert store.verify().ok
    return path


def _lines(path):
    return [ln for ln in path.read_bytes().decode("utf-8").split("\n") if ln.strip()]


def _put(path, lines):
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _edit(path, index, mutate, rehash=False):
    lines = _lines(path)
    rec = json.loads(lines[index])
    mutate(rec)
    if rehash:
        rec["hash"] = compute_event_hash(rec)
    lines[index] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    _put(path, lines)


def _run(*args):
    r = runner.invoke(cli_app, list(args))
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    return r


def _one_tampered_line(r, *, forbidden=()):
    lines = r.stdout.splitlines()
    assert r.exit_code == 1, (r.exit_code, r.stdout)
    assert len(lines) == 1 and lines[0].startswith("TAMPERED — "), lines
    assert ESC not in r.stdout and "\r" not in r.stdout
    for text in forbidden:
        assert text not in r.output, text
    return lines[0]


# ---- B1: the default route ---------------------------------------------------------------------------------------

def test_default_route_an_extra_key_with_the_success_words_is_one_tampered_line(tmp_path):
    path = _plain(tmp_path)
    _edit(path, 2, lambda r: r.update({"x\n" + PHRASE + "\ny": 1}))
    assert PHRASE in path.read_text(encoding="utf-8")
    line = _one_tampered_line(_run("verify", "--path", str(path)), forbidden=(PHRASE, "Extra inputs", "extra_forbidden"))
    assert line == "TAMPERED — unparseable line: ValidationError (the message is not echoed)"


def test_default_route_a_nested_line_is_one_tampered_line_not_a_traceback(tmp_path):
    path = _plain(tmp_path)
    lines = _lines(path)
    lines[3] = "[" * 200000 + "]" * 200000
    _put(path, lines)
    line = _one_tampered_line(_run("verify", "--path", str(path)))
    assert line == "TAMPERED — unparseable line: nesting is deeper than 500 levels"


def test_default_route_a_line_that_is_not_json_is_one_tampered_line(tmp_path):
    path = _plain(tmp_path)
    lines = _lines(path)
    lines[1] = "{not json"
    _put(path, lines)
    line = _one_tampered_line(_run("verify", "--path", str(path)))
    assert line == "TAMPERED — unparseable line: JSONDecodeError (the message is not echoed)"


def test_default_route_the_open_segment_of_a_rotated_ledger_is_covered_too(tmp_path):
    _s, p, _hashes = three_segments(tmp_path / "data" / "ledger")
    _edit(p, 1, lambda r: r.update({"x\n" + PHRASE + "\ny": 1}))
    _one_tampered_line(_run("verify", "--path", str(p)), forbidden=(PHRASE, "Extra inputs"))


def test_default_route_a_hostile_prev_hash_is_one_escaped_line(tmp_path):
    """the main-route TAMPERED site (the reason comes from store.verify(), twelve raw characters of the stored value)"""
    path = _plain(tmp_path)
    _edit(path, 3, lambda r: r.update(prev_hash="ab\n" + FORGED_OK[:8] + "0" * 53))
    line = _one_tampered_line(_run("verify", "--path", str(path)), forbidden=(FORGED_OK,))
    assert "prev_hash ab\\nOK — cha0…" in line                # a backslash and n: the newline, escaped


# ---- B1: the live closed-segment route ---------------------------------------------------------------------------

def _closed(tmp_path):
    _s, p, _hashes = three_segments(tmp_path / "data" / "ledger")
    c = closed_path_for(p, 1)
    assert c.exists() and store_mod.journal_path_for(p).exists()
    return c


def test_closed_segment_route_an_extra_key_is_one_tampered_line(tmp_path):
    c = _closed(tmp_path)
    _edit(c, 1, lambda r: r.update({"x\n" + PHRASE + "\ny": 1}))
    line = _one_tampered_line(_run("verify", "--path", str(c)), forbidden=(PHRASE, "Extra inputs"))
    assert line == "TAMPERED — segment 1: unparseable line: ValidationError (the message is not echoed)"


def test_closed_segment_route_a_nested_line_is_one_tampered_line(tmp_path):
    c = _closed(tmp_path)
    lines = _lines(c)
    lines[2] = "[" * 200000 + "]" * 200000
    _put(c, lines)
    line = _one_tampered_line(_run("verify", "--path", str(c)))
    assert line == "TAMPERED — segment 1: unparseable line: nesting is deeper than 500 levels"


def test_closed_segment_route_a_hostile_prev_hash_is_one_escaped_line(tmp_path):
    """the closed-segment TAMPERED site"""
    c = _closed(tmp_path)
    _edit(c, 2, lambda r: r.update(prev_hash="ab\n" + FORGED_OK[:8] + "0" * 53))
    line = _one_tampered_line(_run("verify", "--path", str(c)), forbidden=(FORGED_OK,))
    assert "prev_hash ab\\nOK — cha0…" in line                # a backslash and n: the newline, escaped


def test_the_function_itself_answers_a_failed_result_not_an_exception(tmp_path):
    c = _closed(tmp_path)
    _edit(c, 1, lambda r: r.update(junk=1))
    got = store_mod.verify_closed_segment(c)
    assert got is not None
    _entry, result = got
    assert result.ok is False and "\n" not in result.reason and result.first_break_index is not None


# ---- B2: --event-pubkey and --caller-keyring --------------------------------------------------------------------

def _signed_last_event(tmp_path, **fields):
    path = _plain(tmp_path)
    hostile = "t\n" + FORGED_OK + "\nz"
    _edit(path, 5, lambda r: r.update(event_type=hostile, event_id="e\n" + FORGED_OK, **fields), rehash=True)
    assert _lines(path)[5].count("999 events") == 2          # the forged words are really in the file
    return path


def test_event_pubkey_a_hostile_event_type_and_id_stay_on_one_line(tmp_path):
    path = _signed_last_event(tmp_path, signature="a" * 128)
    pub = tmp_path / "sign.pub.pem"
    pub.write_text(generate_keypair()[1], encoding="ascii")
    r = _run("verify", "--path", str(path), "--event-pubkey", str(pub))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and lines[0] == "OK — chain intact over 6 events", lines
    assert len(lines) == 2 and lines[1].startswith("SIGNATURE INVALID — index 5: event e\\nOK — chain intact over 999 events (t\\nOK")
    assert ESC not in r.stdout and "\r" not in r.stdout


def test_caller_keyring_an_unknown_caller_with_a_hostile_event_type_stays_on_one_line(tmp_path):
    path = _signed_last_event(tmp_path, caller_id="c1", caller_signature="a" * 128)
    keyring = tmp_path / "keys"
    keyring.mkdir()
    r = _run("verify", "--path", str(path), "--caller-keyring", str(keyring))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and lines[0] == "OK — chain intact over 6 events", lines
    assert len(lines) == 2 and lines[1].startswith("CALLER UNKNOWN — index 5: event e\\nOK — chain intact over 999 events (t\\nOK")


def test_caller_keyring_an_invalid_caller_signature_with_a_hostile_event_type_stays_on_one_line(tmp_path):
    from field_core.signing import generate_keypair as gen

    path = _signed_last_event(tmp_path, caller_id="c1", caller_signature="a" * 128)
    keyring = tmp_path / "keys"
    keyring.mkdir()
    (keyring / "c1.pub.pem").write_text(gen()[1], encoding="ascii")
    r = _run("verify", "--path", str(path), "--caller-keyring", str(keyring))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and lines[0] == "OK — chain intact over 6 events", lines
    assert len(lines) == 2 and lines[1].startswith("CALLER SIGNATURE INVALID — index 5: event e\\nOK")


# ---- the sites the first change routed through _one_line and no test pinned --------------------------------------

def test_anchor_failure_is_one_line(tmp_path, monkeypatch):
    import sealed_ledger.anchors as anchors_mod

    path = _plain(tmp_path)
    pub = tmp_path / "anchor.pub.pem"
    pub.write_text(generate_keypair()[1], encoding="ascii")
    monkeypatch.setattr(anchors_mod, "verify_anchors",
                        lambda *a, **k: SimpleNamespace(ok=False, first_failure="a\n" + FORGED_OK + ESC + "[2J"))
    r = _run("verify", "--path", str(path), "--anchors", str(tmp_path / "anchors.jsonl"), "--pubkey", str(pub))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and lines[0] == "OK — chain intact over 6 events"
    assert lines[1:] == ["ANCHOR FAILURE — a\\nOK — chain intact over 999 events\\x1b[2J"], lines


def test_export_failed_is_one_line(tmp_path, monkeypatch):
    import sealed_ledger.bundle as bundle_mod

    monkeypatch.setattr(bundle_mod, "verify_bundle",
                        lambda *a, **k: SimpleNamespace(ok=False, first_failing_index=3,
                                                        reason="r\n" + FORGED_OK + ESC + "[2J"))
    r = _run("verify-export", str(tmp_path))
    assert r.exit_code == 1
    assert r.stdout.splitlines() == ["EXPORT FAILED — index 3: r\\nOK — chain intact over 999 events\\x1b[2J"]


def test_the_archived_to_text_of_a_pending_move_is_one_line(tmp_path, monkeypatch):
    target = tmp_path / "events-1.jsonl"
    entry = {"n": 1, "start_index": 0, "end_index": 3, "state": "pending-move", "archived_to": "a\n" + FORGED_OK}
    monkeypatch.setattr(store_mod, "verify_closed_segment",
                        lambda p: (entry, SimpleNamespace(ok=True, verified_events=4)))
    r = _run("verify", "--path", str(target))
    lines = r.stdout.splitlines()
    assert r.exit_code == 0
    assert lines[0] == "OK — segment 1 of events.jsonl intact over 4 events (global 0..3)"
    assert lines[1] == ("(archived in the journal to a\\nOK — chain intact over 999 events: a pending move, "
                        "completed by the next retention apply)") and len(lines) == 2


# ---- the served /verify reader (LedgerStore.verify) answers a nested line instead of raising -----------------------

def test_store_verify_answers_a_nested_line_as_a_failed_result(tmp_path):
    path = _plain(tmp_path)
    store = LedgerStore(path)
    lines = _lines(path)
    lines[4] = "[" * 200000 + "]" * 200000
    _put(path, lines)
    result = store.verify()
    assert result.ok is False and result.first_break_index == 4
    assert result.reason.startswith("unparseable record at index 4: JsonTooDeep: nesting is deeper than 500 levels") and "\n" not in result.reason


def test_store_verify_answers_a_nested_line_appended_after_a_cached_parse(tmp_path):
    """the grown-file branch of the parse cache: the new tail is parsed on its own"""
    path = _plain(tmp_path)
    store = LedgerStore(path)
    assert store.verify().ok                                     # parse cached
    with open(path, "ab") as fh:
        fh.write(b"[" * 200000 + b"]" * 200000 + b"\n")
    result = store.verify()
    assert result.ok is False and result.reason.startswith("unparseable record at index 6: JsonTooDeep: nesting is deeper than 500 levels")



# ---- round 3: the escapes the reviewer found unpinned (caller id, verify-witness lines) and the explicit nesting cap ----

def test_caller_keyring_a_hostile_caller_id_stays_on_one_line(tmp_path):
    hostile_id = "c\nOK — chain intact over 5 events" + ESC + "[2J"
    path = _signed_last_event(tmp_path, caller_id=hostile_id, caller_signature="a" * 128)
    keyring = tmp_path / "keys"
    keyring.mkdir()
    r = _run("verify", "--path", str(path), "--caller-keyring", str(keyring))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and lines[0] == "OK — chain intact over 6 events", lines
    assert len(lines) == 2 and lines[1].startswith("CALLER UNKNOWN — index 5: event e\\nOK")
    # the caller id appears twice (the claim and the keyring's own refusal), each time as a backslash-n and \x1b escape
    assert lines[1].count("c\\nOK — chain intact over 5 events\\x1b[2J") == 2, lines[1]
    assert ESC not in r.stdout and "\r" not in r.stdout


def _witness_args(tmp_path, path, events_text="[]"):
    ev = tmp_path / "events.json"
    ev.write_text(events_text, encoding="utf-8")
    return ["verify-witness", "--estate", "e", "--events-file", str(ev), "--path", str(path)]


def test_verify_witness_the_local_chain_reason_is_one_escaped_line(tmp_path):
    path = _plain(tmp_path)
    _edit(path, 3, lambda r: r.update(prev_hash="ab\n" + FORGED_OK[:8] + "0" * 53))
    r = _run(*_witness_args(tmp_path, path))
    lines = r.stdout.splitlines()
    assert r.exit_code == 1 and len(lines) == 1, r.stdout
    assert lines[0].startswith("WITNESS FAILED — the local chain does not verify: link break at index 3: ")
    assert "prev_hash ab\\nOK — cha0…" in lines[0]


def test_verify_witness_the_events_source_refusal_is_one_escaped_line(tmp_path):
    path = _plain(tmp_path)
    key = json.dumps("k\n" + FORGED_OK + ESC + "[2J")
    r = _run(*_witness_args(tmp_path, path, "[{" + key + ": 1, " + key + ": 2}]"))
    assert r.exit_code == 1
    assert r.stdout.splitlines() == [
        "WITNESS FAILED — events source refused: duplicate JSON key 'k\\nOK — chain intact over 999 events\\x1b[2J'"], r.stdout


def test_verify_witness_each_result_line_is_escaped(tmp_path, monkeypatch):
    import sealed_ledger.witness as w

    path = _plain(tmp_path)
    monkeypatch.setattr(w, "verify_witness", lambda *a, **k: SimpleNamespace(
        ok=False, lines=["a\n" + FORGED_OK, "b" + ESC + "[2J"]))
    r = _run(*_witness_args(tmp_path, path))
    assert r.exit_code == 1
    assert r.stdout.splitlines() == ["a\\nOK — chain intact over 999 events", "b\\x1b[2J"], r.stdout


def test_the_nesting_cap_is_explicit_and_independent_of_the_stack(tmp_path):
    """a line one level over the cap is refused by the scan, one at the cap reaches the parser (and fails on its type)"""
    from sealed_ledger.store import JSON_MAX_DEPTH, JsonTooDeep, _parse_events, _parse_events_located

    over = ("[" * (JSON_MAX_DEPTH + 1) + "]" * (JSON_MAX_DEPTH + 1)).encode() + b"\n"
    at = ("[" * JSON_MAX_DEPTH + "]" * JSON_MAX_DEPTH).encode() + b"\n"
    try:
        _parse_events(over)
        raise AssertionError("not refused")
    except JsonTooDeep as exc:
        assert str(exc) == "nesting is deeper than 500 levels"
    try:
        _parse_events(at)
        raise AssertionError("not refused")
    except JsonTooDeep:
        raise AssertionError("refused at the cap")
    except ValueError:
        pass                                           # a list is not a ledger event: ValidationError, not the cap
    _events, bad = _parse_events_located(over)
    assert bad == (0, "JsonTooDeep: nesting is deeper than 500 levels")


def test_a_segment_line_in_another_encoding_is_refused_not_scanned_blind(tmp_path):
    """the line parsers hand the scan and json.loads the same UTF-8 decoded text; a UTF-16 line (U+0122 is bytes 22 01 in
    UTF-16-LE) is a failed verification on any stack, never a parse of a deep value the scan could not see"""
    from sealed_ledger.store import _parse_events, _parse_events_located

    deep = "[" * 100_000 + "]" * 100_000
    for codec in ("utf-16-le", "utf-16-be", "utf-32-le"):
        data = ('{"\u0122": 1, "x": ' + deep + "}\n").encode(codec)
        for fn in (_parse_events,):
            try:
                fn(data)
                raise AssertionError(codec)
            except ValueError:
                pass
        events, bad = _parse_events_located(data)
        assert events == [] and bad is not None and bad[0] == 0


def test_default_route_a_deep_unterminated_last_line_gives_the_cap_text_on_any_stack(tmp_path):
    """the torn-tail probe at store open used json.loads(bytes): a deep unterminated line raised RecursionError on a small
    stack and parsed on a large one, so the TAMPERED text depended on the stack. It now goes through the same cap."""
    path = _plain(tmp_path)
    with open(path, "ab") as fh:
        fh.write(b"[" * 200000 + b"]" * 200000)                       # no trailing newline
    line = _one_tampered_line(_run("verify", "--path", str(path)))
    assert line == "TAMPERED — unparseable line: nesting is deeper than 500 levels"
