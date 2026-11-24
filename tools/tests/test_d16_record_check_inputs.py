"""S9-26: d16_record_check input handling: a non-UTF-8 or empty secret file is exit 2, a blank claimed name is not a name.

`main()` read the --secret-file with `read_text(encoding="utf-8")` under `except OSError`, so a file with bytes 0xff raised
UnicodeDecodeError (a ValueError) out of main as a traceback instead of the documented exit 2; an empty or whitespace-only file
went on as an empty secret and the request was sent without one. And `check_events` counted a claimed name of "   " as present
(`claimed != ""`), although the doc says a row with only the claimed name proves nothing and a blank name is no name.
Nothing here touches a network: the estate is a stub that fails the test if it is reached. Every value is made up."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d16_record_check as dc  # noqa: E402
import estate_probe as ep  # noqa: E402

OP = "don"
H = "0123456789abcdef" * 4


def row(**payload):
    return {"event_type": "kill.revive", "agent_id": "canary-gb10", "hash": H, "payload": payload}


def signed(claimed):
    return row(operator_id_authenticated=OP, operator_claimed=claimed, operator_key_fp="0a1b2c3d")


@pytest.fixture()
def no_network(monkeypatch):
    calls = []

    class Boom:
        def __init__(self, *a, **k):
            calls.append(a)
            raise AssertionError("the estate must not be reached with an unusable secret")

    monkeypatch.setattr(ep, "Estate", Boom)
    return calls


def run_base(tmp_path, capsys, content):
    f = tmp_path / "secret"
    f.write_bytes(content)
    code = dc.main(["--operator-id", OP, "--base", "http://estate.invalid", "--secret-file", str(f)])
    return code, capsys.readouterr().out


@pytest.mark.parametrize("content", [b"\xff\xfe\x00bad", b"\x80\x81", b"ok\xffbytes"], ids=["bom-junk", "high-bytes", "mixed"])
def test_a_non_utf8_secret_file_is_exit_2_not_a_traceback(tmp_path, capsys, no_network, content):
    code, out = run_base(tmp_path, capsys, content)
    assert code == 2 and "the secret file cannot be read" in out
    assert no_network == []


@pytest.mark.parametrize("content", [b"", b"   ", b"\n", b"\r\n\t \n", b"\xef\xbb\xbf"], ids=["empty", "spaces", "newline", "blanks", "bom-only"])
def test_an_empty_or_whitespace_secret_file_is_exit_2_and_nothing_is_sent(tmp_path, capsys, no_network, content):
    code, out = run_base(tmp_path, capsys, content)
    assert code == 2 and "the secret file cannot be read" in out
    assert no_network == []


def test_a_missing_secret_file_is_still_exit_2(tmp_path, capsys, no_network):
    code = dc.main(["--operator-id", OP, "--base", "http://estate.invalid", "--secret-file", str(tmp_path / "absent")])
    assert code == 2 and "the secret file cannot be read" in capsys.readouterr().out and no_network == []


def test_a_good_secret_file_is_stripped_and_reaches_the_estate(tmp_path, capsys, monkeypatch):
    seen = {}

    class Est:
        def __init__(self, base, secret):
            seen["secret"] = secret

        def call(self, method, path):
            return 200, [signed("Don H")]

    monkeypatch.setattr(ep, "Estate", Est)
    code, out = run_base(tmp_path, capsys, b"  made-up-secret-value \r\n")
    assert code == 0 and seen["secret"] == "made-up-secret-value"
    assert "made-up-secret-value" not in out


@pytest.mark.parametrize("blank", ["   ", " ", "\t", "\n", " \t\n ", " ", "　", " "], ids=["3sp", "1sp", "tab", "nl", "mixed", "nbsp", "ideographic", "emspace"])
def test_a_blank_claimed_name_is_not_a_name_and_the_row_fails(blank):
    ok, lines = dc.check_events([signed(blank)], OP)
    assert ok is False
    assert any("claimed name MISSING" in line for line in lines)
    assert any(line.startswith("[FAIL] D16 positive write recorded") for line in lines)


@pytest.mark.parametrize("name", ["Don H", " Don H ", "d", "Don H"])
def test_a_real_claimed_name_still_passes(name):
    ok, lines = dc.check_events([signed(name)], OP)
    assert ok is True and any("claimed name present" in line for line in lines)


def test_the_cli_events_path_fails_a_blank_name_row(tmp_path, capsys):
    f = tmp_path / "events.json"
    f.write_text(json.dumps([signed("   ")]), encoding="utf-8")
    assert dc.main(["--operator-id", OP, "--events", str(f)]) == 1
    assert "claimed name MISSING" in capsys.readouterr().out
