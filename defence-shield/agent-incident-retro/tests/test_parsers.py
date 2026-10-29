from datetime import timezone
from pathlib import Path

import pytest

from agent_incident_retro.parsers import (
    file_sha256,
    line_sha256,
    parse_clf,
    read_input,
    resolve_parser,
    split_lines,
)


def test_split_lines_identity_and_crlf():
    data = b"a\r\nb\n\nc\n"
    got = list(split_lines(data))
    assert got == [(1, b"a"), (2, b"b"), (3, b""), (4, b"c")]
    # the trailing newline does not create a 5th empty line
    assert all(not l.endswith(b"\r") for _, l in got)


def test_split_lines_no_trailing_newline():
    assert list(split_lines(b"only")) == [(1, b"only")]


def test_clf_combined_parses_payload_target():
    line = (
        '203.0.113.5 - - [01/Sep/2026:10:00:45 +0000] '
        '"GET /search?q=%27%20OR%20%271%27%3D%271 HTTP/1.1" 200 812 "-" "curl/8.4"'
    )
    p = parse_clf(line)
    assert p is not None
    assert p.client_ip == "203.0.113.5"
    assert p.status == 200
    assert p.user_agent == "curl/8.4"
    assert p.ts.tzinfo == timezone.utc


def test_clf_quoted_fields_and_dashes():
    line = '198.51.100.9 - - [01/Sep/2026:11:00:00 +0000] "GET / HTTP/1.1" 200 5 "-" "-"'
    p = parse_clf(line)
    assert p is not None and p.user_agent == "" and p.referer == ""


def test_clf_rejects_garbage():
    assert parse_clf("not a log line") is None
    assert parse_clf("") is None


def test_jsonl_generic_and_unix_ms_timestamp():
    parse = resolve_parser("jsonl", "generic")
    row = '{"timestamp": 1788256845000, "client_ip":"203.0.113.5","method":"GET","uri":"/a?x=1","status":200,"user_agent":"x"}'
    p = parse(row)
    assert p is not None and p.status == 200 and p.ts.year == 2026 and p.ts.month == 9


def test_jsonl_full_url_reduced_to_path(tmp_path: Path):
    parse = resolve_parser("jsonl", "generic")
    p = parse('{"ts":"2026-09-01T00:00:00Z","ip":"203.0.113.5","uri":"https://h/x?y=1","status":200}')
    assert p is not None and p.target.startswith("/x")


def test_read_input_counts_and_hashes(tmp_path: Path):
    log = tmp_path / "a.log"
    good = '203.0.113.5 - - [01/Sep/2026:10:00:45 +0000] "GET /x HTTP/1.1" 200 1 "-" "ua"'
    log.write_text(good + "\nnot-a-line\n", encoding="utf-8")
    info, requests = read_input(log, "a.log", "clf", resolve_parser("clf"))
    assert info.parsed == 1 and info.unparsed == 1
    assert info.sha256 == file_sha256(log.read_bytes())
    assert requests[0].ref.sha256 == line_sha256(good.encode("utf-8"))


# ---------------------------------------------------------------------------
# SPEC §3.1 "unparseable lines are never fatal" (second independent review,
# 2026-10-12, MEDIUM-1). Each of these made the stdlib raise something other
# than the ValueError / JSONDecodeError the parsers caught.

_CLF = '{ip} - - [{ts}] "GET /x HTTP/1.1" 200 1 "-" "ua"'
_J = '{{"ts":{ts},"ip":"1.1.1.1","uri":"/","status":{status}{extra}}}'

NESTED_IN_FIELD = "jsonl 100k nested brackets in a field"

HOSTILE_LINES = {
    "clf year 9999 with offset (OverflowError in astimezone)": ("clf", _CLF.format(ip="1.1.1.1", ts="31/Dec/9999:23:00:00 -0500")),
    "clf year 0001 with offset (OverflowError in astimezone)": ("clf", _CLF.format(ip="1.1.1.1", ts="01/Jan/0001:01:00:00 +0500")),
    "jsonl iso year 9999 with offset": ("jsonl", _J.format(ts='"9999-12-31T23:00:00-05:00"', status=200, extra="")),
    "jsonl iso year 0001 with offset": ("jsonl", _J.format(ts='"0001-01-01T01:00:00+05:00"', status=200, extra="")),
    "jsonl 5000-digit int (ValueError, not JSONDecodeError)": ("jsonl", _J.format(ts='"2026-09-01T00:00:00Z"', status=200, extra=',"n":' + "1" * 5000)),
    "jsonl 5000-digit status": ("jsonl", _J.format(ts='"2026-09-01T00:00:00Z"', status="2" * 5000, extra="")),
    "jsonl 100k nested brackets (RecursionError)": ("jsonl", "[" * 100_000),
    "jsonl 100k nested brackets in a field": ("jsonl", _J.format(ts='"2026-09-01T00:00:00Z"', status=200, extra=',"x":' + "[" * 100_000 + "]" * 100_000)),
    "jsonl status 1e400 (OverflowError: inf to int)": ("jsonl", _J.format(ts='"2026-09-01T00:00:00Z"', status="1e400", extra="")),
    "jsonl status NaN": ("jsonl", _J.format(ts='"2026-09-01T00:00:00Z"', status="NaN", extra="")),
    "jsonl ts 6000-digit string": ("jsonl", _J.format(ts='"' + "9" * 6000 + '"', status=200, extra="")),
}


@pytest.mark.parametrize("label", sorted(HOSTILE_LINES))
def test_hostile_line_is_unparsed_not_fatal(label: str, tmp_path: Path):
    fmt, line = HOSTILE_LINES[label]
    parser = resolve_parser(fmt, "generic")
    result = parser(line)  # the direct call does not raise
    if label != NESTED_IN_FIELD:
        assert result is None
    # NESTED_IN_FIELD is a valid JSON record on interpreters whose json module has no
    # nesting limit (CPython 3.14: CI run 40788927359): the line then parses, with the
    # nested value ignored. Where the module raises RecursionError the guard returns None.
    # Either way the line is accounted for and never fatal.
    good = (
        '203.0.113.5 - - [01/Sep/2026:10:00:45 +0000] "GET /x HTTP/1.1" 200 1 "-" "ua"'
        if fmt == "clf"
        else '{"ts":"2026-09-01T00:00:00Z","ip":"203.0.113.5","uri":"/x","status":200}'
    )
    log = tmp_path / f"h.{fmt}"
    log.write_text(line + "\n" + good + "\n", encoding="utf-8")
    info, requests = read_input(log, log.name, fmt, parser)
    unparsed = 1 if result is None else 0
    assert (info.lines, info.parsed, info.unparsed) == (2, 2 - unparsed, unparsed)
    assert requests[-1].ref.line == 2  # the good line keeps its own number


def test_never_fatal_does_not_swallow_base_exceptions():
    """The guard catches Exception, not BaseException: Ctrl-C and the tests'
    no-network tripwire must still propagate through a parser."""
    from agent_incident_retro.parsers import never_fatal

    class Trip(BaseException):
        pass

    @never_fatal
    def boom(_: str):
        raise Trip

    with pytest.raises(Trip):
        boom("x")


def test_jsonl_duplicate_keys_last_wins():
    """Documented in LIMITS: json.loads keeps the LAST of duplicate keys, so a
    record with two "ip" fields is attributed to the second one."""
    parse = resolve_parser("jsonl", "generic")
    p = parse('{"ts":"2026-09-01T00:00:00Z","ip":"1.1.1.1","ip":"9.9.9.9","uri":"/","status":200}')
    assert p is not None and p.client_ip == "9.9.9.9"
