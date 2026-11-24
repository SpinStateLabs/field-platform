"""B-1029-CLI-LEAK: `ledger verify-witness` must not echo what is wrong INSIDE a secret file.

A --secret-file that is not UTF-8 raised UnicodeDecodeError, and the CLI printed ``{exc}``: "'utf-8' codec can't
decode byte 0xff in position 25: invalid start byte". Position 25 is the length of the secret before the bad byte,
and 0xff is one raw byte of it. Now only the exception TYPE is printed (as the rest of this command already does)
and the exit code stays 2.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sealed_ledger.cli import app as cli_app

runner = CliRunner()
SECRET_HEAD = b"s3cr3t-prefix-0123456789a"           # 25 bytes
assert len(SECRET_HEAD) == 25


def _run(tmp_path, secret_bytes, *extra):
    sf = tmp_path / "secret.txt"
    sf.write_bytes(secret_bytes)
    return runner.invoke(cli_app, ["verify-witness", "--estate", "e", "--events-url", "https://127.0.0.1:9/events",
                                   "--secret-file", str(sf), "--path", str(tmp_path / "events.jsonl"), *extra])


@pytest.mark.parametrize("bad", [b"\xff", b"\x80", b"\xc3\x28"])
def test_a_non_utf8_secret_file_exits_2_and_prints_neither_the_position_nor_the_byte(tmp_path, bad):
    r = _run(tmp_path, SECRET_HEAD + bad + b"tail")
    assert r.exit_code == 2, r.output
    out = r.output
    assert "UnicodeDecodeError" in out                                  # the type is still named
    assert "position" not in out and "0x" not in out and "invalid" not in out
    assert "25" not in out                                              # the secret's length
    assert "s3cr3t" not in out


def test_the_message_names_the_secret_file_not_the_events_source(tmp_path):
    r = _run(tmp_path, SECRET_HEAD + b"\xff")
    assert r.exit_code == 2
    assert "--secret-file" in r.output


def test_an_unreadable_secret_file_path_exits_2_without_the_os_message_detail(tmp_path):
    r = runner.invoke(cli_app, ["verify-witness", "--estate", "e", "--events-url", "https://127.0.0.1:9/events",
                                "--secret-file", str(tmp_path / "missing.txt"), "--path", str(tmp_path / "e.jsonl")])
    assert r.exit_code == 2, r.output


def test_a_events_file_that_is_not_utf8_also_prints_only_the_type(tmp_path):
    ef = tmp_path / "events.json"
    ef.write_bytes(b"x" * 25 + b"\xff")
    r = runner.invoke(cli_app, ["verify-witness", "--estate", "e", "--events-file", str(ef),
                                "--path", str(tmp_path / "events.jsonl")])
    assert r.exit_code == 2, r.output
    assert "position" not in r.output and "0xff" not in r.output
