"""Scout S-2-10: `witness.load_events` split a JSONL events file with `str.splitlines()`, which also breaks on U+2028,
U+2029, U+0085 (NEL), VT, FF and U+001C/D/E/F. JSON allows those raw inside a string, so an event whose payload carries
one was cut in two and the file failed to parse ('events source unreadable', exit 2). The rest of the package splits on
`\\n` only (bundle.py, anchors.py, the store's own reader); this pins load_events to the same boundary."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from sealed_ledger import witness as w
from sealed_ledger.cli import app as cli_app

#: Legal raw inside a JSON string, and a line break to str.splitlines(): the ones that cut an event.
SEPARATORS = {"U+2028": chr(0x2028), "U+2029": chr(0x2029), "NEL": chr(0x85)}
#: Control characters splitlines() also breaks on. JSON forbids them raw in a string, so a writer emits them escaped
#: (backslash-u000b and so on) and they never reach the splitter; pinned so a change on either side shows.
CONTROL = {"VT": chr(0x0B), "FF": chr(0x0C), "FS": chr(0x1C), "GS": chr(0x1D), "RS": chr(0x1E)}


def _event(i: int, note: str = "x") -> dict:
    return {"event_type": "anchor.remote", "agent_id": "witness",
            "payload": {"estate": "gb10", "length": i, "head_hash": "a" * 64, "note": note}}


def _jsonl(events: list[dict]) -> bytes:
    # ensure_ascii=False keeps the separators raw in the line, as a writer that does not escape them would
    return ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode("utf-8")


@pytest.mark.parametrize("name", sorted(SEPARATORS))
def test_an_event_with_a_raw_separator_in_a_string_is_one_event(name):
    sep = SEPARATORS[name]
    events = [_event(1), _event(2, note=f"before{sep}after"), _event(3)]
    raw = _jsonl(events)
    assert sep.encode("utf-8") in raw
    assert w.load_events(raw) == events


def test_several_separators_in_one_event_and_across_events():
    events = [_event(1, note="\u2028\u2029"), _event(2, note="a\u0085b\u2028c")]
    assert w.load_events(_jsonl(events)) == events


@pytest.mark.parametrize("name", sorted(CONTROL))
def test_a_control_character_in_a_string_travels_escaped_and_stays_one_event(name):
    ch = CONTROL[name]
    events = [_event(1), _event(2, note=f"a{ch}b"), _event(3)]
    raw = _jsonl(events)
    assert ch.encode("utf-8") not in raw          # json.dumps escapes it; a raw one is invalid JSON
    assert w.load_events(raw) == events
    with pytest.raises(ValueError):               # a RAW one is refused as invalid JSON, never mis-split
        w.load_events(f'{{"note": "a{ch}b"}}\n'.encode("utf-8"))


def test_blank_lines_and_a_missing_final_newline_still_work():
    events = [_event(1), _event(2, note="p\u2028q")]
    raw = _jsonl(events).rstrip(b"\n")
    assert w.load_events(raw) == events
    assert w.load_events(b"\n\n" + raw + b"\n\n") == events


def test_the_json_array_form_is_unchanged():
    events = [_event(1, note="p\u2028q"), _event(2)]
    assert w.load_events(json.dumps(events, ensure_ascii=False).encode("utf-8")) == events


def test_a_crlf_line_ending_is_still_read():
    events = [_event(1), _event(2)]
    raw = "\r\n".join(json.dumps(e) for e in events).encode("utf-8") + b"\r\n"
    assert w.load_events(raw) == events


def test_a_truly_broken_line_is_still_refused():
    with pytest.raises(ValueError):
        w.load_events(b'{"a": 1}\n{not json}\n')


def test_a_duplicate_key_is_still_refused():
    with pytest.raises(w.DuplicateKey):
        w.load_events(b'{"a": 1, "a": 2}\n')


def test_verify_witness_cli_does_not_report_a_valid_events_file_as_unreadable(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_bytes(_jsonl([_event(1, note="line\u2028break"), _event(2)]))
    result = CliRunner().invoke(cli_app, ["verify-witness", "--estate", "gb10", "--events-file", str(f),
                                          "--path", str(tmp_path / "ledger")])
    assert "events source unreadable" not in result.output
    assert result.exit_code != 2, result.output
