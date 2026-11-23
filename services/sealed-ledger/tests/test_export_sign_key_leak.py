"""B-EXPORT-KEY-BYTE-LEAK: `ledger export --sign-key` must not echo a decode error's byte and offset.

A key file that is not ASCII raised UnicodeDecodeError ("'ascii' codec can't decode byte 0xff in position 25 ..."),
which printed one raw byte of the key and the length of what precedes it. Now a fixed message names only the option.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sealed_ledger.cli import app as cli_app

runner = CliRunner()
HEAD = b"-----BEGIN-key-material-0"        # 25 bytes
assert len(HEAD) == 25


def _export(tmp_path, key_bytes):
    key = tmp_path / "key.pem"
    key.write_bytes(key_bytes)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b"")
    return runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(tmp_path / "out"),
                                   "--sign-key", str(key)])


@pytest.mark.parametrize("bad", [b"\xff", b"\x80", b"\xc3\x28"])
def test_a_non_ascii_key_file_prints_a_fixed_message_without_byte_or_offset(tmp_path, bad):
    r = _export(tmp_path, HEAD + bad + b"tail")
    assert r.exit_code == 2, r.output
    out = r.output
    assert "--sign-key" in out
    for leak in ("position", "0x", "codec", "invalid", "25", "BEGIN-key", "UnicodeDecodeError"):
        assert leak not in out, (leak, out)
    assert not (tmp_path / "out").exists()


def test_a_missing_key_file_keeps_the_usage_error_and_names_no_os_detail(tmp_path):
    r = runner.invoke(cli_app, ["export", "--path", str(tmp_path / "l.jsonl"), "--out-dir", str(tmp_path / "x"),
                                "--sign-key", str(tmp_path / "nope.pem")])
    assert r.exit_code == 2 and "cannot read --sign-key" in r.output
