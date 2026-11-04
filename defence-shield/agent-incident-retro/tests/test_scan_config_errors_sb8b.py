"""`retro scan` with a bad --config or an unreadable key exits 1 with a one-line error, never a
traceback (scout S-B8, second half). Before: a missing --config file raised FileNotFoundError out
of `_load_config` (only ValueError was caught); a config that is JSON but not an object (a list,
null, a string, a number) raised TypeError; a key path that is a directory raised
IsADirectoryError (only FileNotFoundError was caught after the scan)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_incident_retro.cli import app
from agent_incident_retro.synth import generate

runner = CliRunner()
MARK = "zz-marker-do-not-echo"


@pytest.fixture
def env(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    return {"log": log, "key": tmp_path / "k", "out": tmp_path / "out", "dir": tmp_path}


def _scan(env, *extra, key=None):
    return runner.invoke(app, ["scan", str(env["log"]), "--out", str(env["out"]),
                               "--key", str(key or env["key"]), *extra])


def _clean_error(r):
    assert r.exit_code == 1, r.output
    assert isinstance(r.exception, SystemExit) or r.exception is None, repr(r.exception)
    assert "error" in r.output.lower() and "Traceback" not in r.output


def test_a_missing_config_file_is_a_clean_error(env):
    _clean_error(_scan(env, "--config", str(env["dir"] / "nope.json")))


def test_a_config_that_is_a_directory_is_a_clean_error(env):
    _clean_error(_scan(env, "--config", str(env["dir"])))


@pytest.mark.parametrize("body", ["[]", "null", '"text"', "5", "true", "[1, 2]"])
def test_a_config_that_is_json_but_not_an_object_is_a_clean_error(env, body):
    cfg = env["dir"] / "cfg.json"
    cfg.write_text(body, encoding="utf-8")
    r = _scan(env, "--config", str(cfg))
    _clean_error(r)
    assert "object" in r.output.lower()


@pytest.mark.parametrize("body", ["{not json", "", '{"a": '])
def test_invalid_json_stays_a_clean_error(env, body):
    cfg = env["dir"] / "cfg.json"
    cfg.write_text(body, encoding="utf-8")
    _clean_error(_scan(env, "--config", str(cfg)))


def test_a_non_utf8_config_is_a_clean_error(env):
    cfg = env["dir"] / "cfg.json"
    cfg.write_bytes(b"\xff\xfe\x00bad")
    _clean_error(_scan(env, "--config", str(cfg)))


def test_the_error_does_not_echo_the_config_content(env):
    cfg = env["dir"] / "cfg.json"
    cfg.write_text(json.dumps([MARK]), encoding="utf-8")
    assert MARK not in _scan(env, "--config", str(cfg)).output


def test_a_key_path_that_is_a_directory_is_a_clean_error(env):
    _clean_error(_scan(env, key=env["dir"]))


def test_a_missing_key_file_is_still_a_clean_error(env):
    _clean_error(_scan(env, key=env["dir"] / "no-such.key"))


def test_a_valid_object_config_still_scans(env):
    cfg = env["dir"] / "cfg.json"
    cfg.write_text(json.dumps({"session_gap_s": 120}), encoding="utf-8")
    r = _scan(env, "--config", str(cfg))
    assert r.exit_code in (0, 2, 3), r.output          # 2 = ESCALATE found, 3 = AUTHORIZED only
    assert isinstance(r.exception, SystemExit) or r.exception is None
    assert (env["out"] / "report.md").exists()
