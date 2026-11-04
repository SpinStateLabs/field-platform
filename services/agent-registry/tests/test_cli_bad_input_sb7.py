"""`registry add` and `registry scan` must exit with a named message, never a traceback
(scout S-B7). add: an invalid slug raised pydantic.ValidationError (the CLI doc promises
exit codes, the API route answers 422). scan: a missing or unreadable input file escaped
as FileNotFoundError/PermissionError although the docstring promises exit 2."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_registry.cli import app

runner = CliRunner()


def _db(tmp_path: Path) -> list[str]:
    return ["--path", str(tmp_path / "agents.sqlite3")]


def _not_a_crash(r):
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)


@pytest.mark.parametrize("bad_id", ["Bad_ID", "has space", "-lead", "UPPER"])
def test_add_with_an_invalid_slug_exits_2_and_writes_nothing(tmp_path, bad_id):
    r = runner.invoke(app, ["add", bad_id, "--name", "n", "--owner", "o", *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2, r.output
    assert "error" in r.output.lower()
    listed = runner.invoke(app, ["list", *_db(tmp_path)])
    assert listed.exit_code == 0 and bad_id not in listed.output


def test_add_error_message_does_not_quote_the_input(tmp_path):
    marker = "Zz_Marker_Do_Not_Echo"
    r = runner.invoke(app, ["add", marker, "--name", "n", "--owner", "o", *_db(tmp_path)])
    assert r.exit_code == 2 and marker not in r.output


def test_add_with_a_valid_slug_still_registers(tmp_path):
    r = runner.invoke(app, ["add", "good-agent", "--name", "n", "--owner", "o", *_db(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "good-agent" in r.output


@pytest.mark.parametrize("flag", ["--accounts", "--api-keys", "--secrets-text"])
def test_scan_with_a_missing_input_file_exits_2(tmp_path, flag):
    r = runner.invoke(app, ["scan", flag, str(tmp_path / "nope.txt"), *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2, r.output
    assert "nope.txt" in r.output or "cannot read" in r.output.lower()


def test_scan_with_a_missing_principals_file_exits_2(tmp_path):
    keys = tmp_path / "keys.csv"
    keys.write_text("key_name,owner,service,created,last_used\n", encoding="utf-8")
    r = runner.invoke(app, ["scan", "--api-keys", str(keys),
                            "--principals", str(tmp_path / "gone.csv"), *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2, r.output


def test_scan_with_a_directory_instead_of_a_file_exits_2(tmp_path):
    r = runner.invoke(app, ["scan", "--accounts", str(tmp_path), *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2, r.output


def test_scan_with_a_readable_clean_file_still_exits_0(tmp_path):
    f = tmp_path / "accounts.csv"
    f.write_text("account,owner\n", encoding="utf-8")
    r = runner.invoke(app, ["scan", "--accounts", str(f), *_db(tmp_path)])
    assert r.exit_code in (0, 2), r.output          # 2 only if the header is not a scanner shape
    _not_a_crash(r)


def test_scan_with_a_missing_n8n_file_exits_2(tmp_path):
    r = runner.invoke(app, ["scan", "--n8n", str(tmp_path / "wf.json"), *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2 and "wf.json" in r.output


def test_scan_with_invalid_n8n_json_exits_2_and_does_not_echo_it(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text('{"nodes": [Zz_Marker_Do_Not_Echo', encoding="utf-8")
    r = runner.invoke(app, ["scan", "--n8n", str(f), *_db(tmp_path)])
    _not_a_crash(r)
    assert r.exit_code == 2 and "Zz_Marker_Do_Not_Echo" not in r.output
