"""provision_ssl_agents: a bad tokens file or a bad TTL stops the run BEFORE anything is
sent (scout S-A6). Before: FIELD_TOKEN_TTL_DAYS=abc raised ValueError at import; a tokens
file holding a list or null failed only at `tokens[agent_id] = ...`, after the tokens were
minted (and so never saved); corrupt JSON was a traceback. The messages name the problem
and never echo the file's content or the variable's value."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "provision_ssl_agents.py"


class _Reached(Exception):
    pass


def _load(monkeypatch, **env):
    for k in ("FIELD_TOKEN_TTL_DAYS", "FIELD_TOKENS_FILE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("FIELD_PROXY_URL", "http://proxy.invalid:18080")
    spec = importlib.util.spec_from_file_location("provision_ssl_agents_sa6", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guard(tool, monkeypatch):
    """health is the first request: reaching it means validation passed."""
    monkeypatch.setattr(tool, "health", lambda *a, **k: (_ for _ in ()).throw(_Reached()))
    monkeypatch.setattr(tool, "client", lambda *a, **k: pytest.fail("a client was built"))


MARKER = "zz-marker-do-not-echo"


@pytest.mark.parametrize("raw", ["abc", "1.5", "0", "-3", "30days", MARKER, "1e3"])
def test_a_bad_ttl_does_not_crash_the_import_and_stops_the_run_before_any_request(
        monkeypatch, capsys, tmp_path, raw):
    tool = _load(monkeypatch, FIELD_TOKEN_TTL_DAYS=raw, FIELD_TOKENS_FILE=str(tmp_path / "t.json"))
    _guard(tool, monkeypatch)
    assert tool.main([]) == 2
    err = capsys.readouterr().err
    assert "FIELD_TOKEN_TTL_DAYS" in err and "Nothing was sent" in err
    assert MARKER not in err and "abc" not in err
    assert not (tmp_path / "t.json").exists()


@pytest.mark.parametrize("raw,want", [("1", 1), ("30", 30), ("365", 365), (" 14 ", 14), ("", 30), ("  ", 30)])
def test_a_good_ttl_is_used(monkeypatch, tmp_path, raw, want):
    tool = _load(monkeypatch, FIELD_TOKEN_TTL_DAYS=raw, FIELD_TOKENS_FILE=str(tmp_path / "t.json"))
    assert tool.TTL_DAYS == want


def test_the_default_ttl_is_thirty_days(monkeypatch, tmp_path):
    assert _load(monkeypatch, FIELD_TOKENS_FILE=str(tmp_path / "t.json")).TTL_DAYS == 30


@pytest.mark.parametrize("body", ["[]", "null", '"x"', "5", '{"a": 1}', '{"a": null}', '{"a": ["x"]}',
                                  "{not json", "", '{"a": "ok"', "﻿[]"])
def test_a_bad_tokens_file_stops_the_run_before_any_request_and_is_left_untouched(
        monkeypatch, capsys, tmp_path, body):
    f = tmp_path / "t.json"
    f.write_text(body, encoding="utf-8")
    tool = _load(monkeypatch, FIELD_TOKENS_FILE=str(f))
    _guard(tool, monkeypatch)
    assert tool.main([]) == 2
    err = capsys.readouterr().err
    assert "tokens file" in err and "Nothing was sent" in err
    assert f.read_text(encoding="utf-8") == body            # never overwritten


def test_a_non_utf8_tokens_file_stops_the_run_cleanly(monkeypatch, capsys, tmp_path):
    f = tmp_path / "t.json"
    f.write_bytes(b"\xff\xfe\x00bad")
    tool = _load(monkeypatch, FIELD_TOKENS_FILE=str(f))
    _guard(tool, monkeypatch)
    assert tool.main([]) == 2 and "tokens file" in capsys.readouterr().err


def test_a_tokens_file_that_is_a_directory_stops_the_run_cleanly(monkeypatch, capsys, tmp_path):
    tool = _load(monkeypatch, FIELD_TOKENS_FILE=str(tmp_path))
    _guard(tool, monkeypatch)
    assert tool.main([]) == 2 and "tokens file" in capsys.readouterr().err


def test_the_error_never_echoes_the_file_content(monkeypatch, capsys, tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"a": MARKER, "b": 5}), encoding="utf-8")
    tool = _load(monkeypatch, FIELD_TOKENS_FILE=str(f))
    _guard(tool, monkeypatch)
    assert tool.main([]) == 2
    out = capsys.readouterr()
    assert MARKER not in out.err and MARKER not in out.out


@pytest.mark.parametrize("body", [None, "{}", '{"ssl-timekeeping-agent": "tok-1"}'])
def test_a_missing_empty_or_valid_tokens_file_proceeds_to_the_first_request(monkeypatch, tmp_path, body):
    f = tmp_path / "t.json"
    if body is not None:
        f.write_text(body, encoding="utf-8")
    tool = _load(monkeypatch, FIELD_TOKENS_FILE=str(f))
    _guard(tool, monkeypatch)
    with pytest.raises(_Reached):
        tool.main([])
