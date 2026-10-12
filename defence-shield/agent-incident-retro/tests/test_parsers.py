from datetime import timezone
from pathlib import Path

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
