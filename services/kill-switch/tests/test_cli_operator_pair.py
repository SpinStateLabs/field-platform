"""S9-15: kill_switch.cli.operator_pair and _read_key_file, called directly (precedence, refusals, never printing the key),
plus one CliRunner pass through the real `agent` verb: a refused pair sends nothing, a good pair rides only the guarded
POST /kill/{id}. The halt CLI is the break-glass path, so a silently wrong identity is a live-incident failure. Every
value is made up."""
from __future__ import annotations

import httpx
import pytest
import typer
from typer.testing import CliRunner

from kill_switch import cli

KEY = "fok_made-up-key-0123456789abcdef"
ENV_KEY = "fok_made-up-ENV-KEY-0123456789"
FILE_KEY = "fok_made-up-FILE-KEY-0123456789"
runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE", "FIELD_AUTH_SECRET"):
        monkeypatch.delenv(name, raising=False)


def keyfile(tmp_path, content: bytes, name="key"):
    p = tmp_path / name
    p.write_bytes(content)
    return p


def refused(fn, capsys, secret=None):
    with pytest.raises(typer.Exit) as exc:
        fn()
    out = capsys.readouterr()
    assert exc.value.exit_code == 2
    if secret:
        assert secret not in out.out + out.err
    return out.err


def test_nothing_configured_returns_none():
    assert cli.operator_pair(None, None) is None


def test_env_only_is_used(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair(None, None) == ("env-op", ENV_KEY)


def test_flags_win_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair("flag-op", keyfile(tmp_path, FILE_KEY.encode())) == ("flag-op", FILE_KEY)


def test_the_key_file_variable_wins_over_the_key_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(keyfile(tmp_path, FILE_KEY.encode())))
    assert cli.operator_pair(None, None) == ("env-op", FILE_KEY)


@pytest.mark.parametrize("content", [b"", b"x" * 4097, b"\xff\xfe\x00bad", b"two tokens"], ids=["empty", "big", "not-utf8", "multi"])
def test_an_unusable_env_key_file_never_falls_back_to_the_variable(monkeypatch, tmp_path, capsys, content):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(keyfile(tmp_path, content)))
    assert cli.operator_pair(None, None) is None
    out = capsys.readouterr()
    assert "warning: FIELD_OPERATOR_KEY_FILE is" in out.err and ENV_KEY not in out.out + out.err


def test_a_missing_env_key_file_warns_and_returns_none(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(tmp_path / "absent"))
    assert cli.operator_pair(None, None) is None
    assert "unreadable" in capsys.readouterr().err


@pytest.mark.parametrize("content,problem", [(None, "unreadable (FileNotFoundError)"), (b"", "empty"), (b"x" * 4097, "larger than a key"),
                                             (b"\xff\xfe\x00", "not UTF-8"), (b"two tokens", "not a single key token")],
                         ids=["missing", "empty", "big", "not-utf8", "multi"])
def test_an_explicit_bad_key_file_exits_2_naming_the_problem(tmp_path, capsys, content, problem):
    path = tmp_path / "absent" if content is None else keyfile(tmp_path, content)
    err = refused(lambda: cli.operator_pair("op", path), capsys)
    assert f"--operator-key-file is {problem}; nothing sent" in err and "FIELD_OPERATOR_KEY_FILE" not in err


def test_a_bom_and_trailing_newline_are_stripped(tmp_path):
    assert cli.operator_pair("op", keyfile(tmp_path, b"\xef\xbb\xbf" + KEY.encode() + b"\r\n")) == ("op", KEY)


def test_an_id_without_a_key_exits_2(capsys):
    assert "go together" in refused(lambda: cli.operator_pair("op", None), capsys)


def test_a_key_without_an_id_exits_2(tmp_path, capsys):
    assert "go together" in refused(lambda: cli.operator_pair(None, keyfile(tmp_path, KEY.encode())), capsys, KEY)


@pytest.mark.parametrize("op", ["bad id", "a/b", "x" * 65, "é"], ids=repr)
def test_an_invalid_id_exits_2(tmp_path, capsys, op):
    assert "not a valid operator id" in refused(lambda: cli.operator_pair(op, keyfile(tmp_path, KEY.encode())), capsys, KEY)


def test_an_invalid_env_key_shape_exits_2_without_showing_it(monkeypatch, capsys):
    bad = "bad key with spaces"
    monkeypatch.setenv("FIELD_OPERATOR", "op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", bad)
    err = refused(lambda: cli.operator_pair(None, None), capsys, bad)
    assert "value not shown" in err


# -- through the real `agent` verb ---------------------------------------------------------------------------------------
@pytest.fixture()
def wire(monkeypatch):
    """The real _client (GuardedOperatorAuth included) over a recording MockTransport."""
    seen: list[httpx.Request] = []
    real = httpx.Client

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"killed": True})

    monkeypatch.setattr(cli.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def test_a_refused_pair_sends_no_request_at_all(wire, tmp_path):
    res = runner.invoke(cli.app, ["agent", "a1", "--operator", "h", "--reason", "r", "--operator-id", "op",
                                  "--operator-key-file", str(tmp_path / "absent")])
    assert res.exit_code == 2 and wire == []


def test_a_good_pair_rides_the_guarded_kill_post_and_not_the_heartbeat_get(wire, tmp_path):
    res = runner.invoke(cli.app, ["agent", "a1", "--operator", "h", "--reason", "r", "--operator-id", "op",
                                  "--operator-key-file", str(keyfile(tmp_path, KEY.encode()))])
    assert res.exit_code == 0 and len(wire) == 1
    assert wire[0].method == "POST" and wire[0].url.path == "/kill/a1"
    assert wire[0].headers["x-field-operator"] == "op" and wire[0].headers["x-field-operator-key"] == KEY
    assert KEY not in res.output
    runner.invoke(cli.app, ["heartbeat", "a1"])
    assert wire[1].method == "GET" and "x-field-operator" not in wire[1].headers and "x-field-operator-key" not in wire[1].headers
