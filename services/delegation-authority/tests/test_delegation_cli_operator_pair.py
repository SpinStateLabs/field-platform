"""S9-6 card (B-S9-14): `delegation_authority.cli.operator_pair` and `_read_key_file`, called directly.

The block is a copy of the one in the kill-switch and lifecycle CLIs (only lifecycle's copy had coverage), so a drift here was
undetected. It holds seven refusal or precedence branches: the flags win over the environment; FIELD_OPERATOR_KEY_FILE wins over
FIELD_OPERATOR_KEY and an unusable env file never falls back to the variable (a warning, no identity); a key file named on the
command line that is missing, empty, over 4096 bytes, not UTF-8 or more than one token exits 2; an id without a key (or the
reverse) exits 2; a bad id or key exits 2 with "value not shown". The key text never appears in any output. All values are made up."""

import pytest
import typer

from delegation_authority import cli

KEY = "fok_MADE-UP-key-0123456789abcdef"
ENV_KEY = "fok_ENV-made-up-key-0123456789"
FILE_KEY = "fok_FILE-made-up-key-0123456789"
ALL = (KEY, ENV_KEY, FILE_KEY)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)


def keyfile(tmp_path, content, name="key"):
    p = tmp_path / name
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return str(p)


def refuses(capsys, *args, **kw):
    with pytest.raises(typer.Exit) as exc:
        cli.operator_pair(*args, **kw)
    assert exc.value.exit_code == 2
    out = capsys.readouterr()
    for secret in ALL:
        assert secret not in out.out + out.err
    return out.err


# -- precedence ------------------------------------------------------------------------------------------------------

def test_neither_id_nor_key_is_none():
    assert cli.operator_pair(None, None) is None


def test_the_environment_pair_is_used_when_no_flag_is_given(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair(None, None) == ("env-op", ENV_KEY)


def test_the_flags_win_over_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair("flag-op", keyfile(tmp_path, FILE_KEY)) == ("flag-op", FILE_KEY)


def test_a_flag_id_with_the_environment_key_is_a_pair(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair("flag-op", None) == ("flag-op", ENV_KEY)


def test_the_env_key_file_wins_over_the_env_key_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", keyfile(tmp_path, FILE_KEY))
    assert cli.operator_pair(None, None) == ("env-op", FILE_KEY)


@pytest.mark.parametrize("content", [b"", b"   \n", b"two words", b"\xff\xfe\x00bad", b"k" * 4097],
                         ids=["empty", "blank", "two-tokens", "not-utf8", "oversize"])
def test_an_unusable_env_key_file_never_falls_back_to_the_variable_and_warns(monkeypatch, tmp_path, capsys, content):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", keyfile(tmp_path, content))
    assert cli.operator_pair(None, None) is None
    err = capsys.readouterr().err
    assert err.startswith("warning: FIELD_OPERATOR_KEY_FILE is ") and "no operator identity is sent" in err
    assert ENV_KEY not in err


def test_a_missing_env_key_file_warns_and_returns_none(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(tmp_path / "absent"))
    assert cli.operator_pair(None, None) is None
    assert "unreadable (FileNotFoundError)" in capsys.readouterr().err


def test_an_env_key_file_without_an_operator_id_is_ignored_silently(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", keyfile(tmp_path, FILE_KEY))
    assert cli.operator_pair(None, None) is None
    assert capsys.readouterr().err == ""


# -- the key file named on the command line is strict -----------------------------------------------------------------

@pytest.mark.parametrize("content, word", [(b"", "empty"), (b"  \n\t", "empty"), (b"two words", "not a single key token"),
                                           (b"\xff\xfe\x00bad", "not UTF-8"), (b"k" * 4097, "larger than a key"),
                                           (b"key;semi", "not a single key token")],
                         ids=["empty", "blank", "two-tokens", "not-utf8", "oversize", "semicolon"])
def test_a_flag_key_file_that_is_unusable_exits_2_naming_the_problem_never_the_content(tmp_path, capsys, content, word):
    err = refuses(capsys, "flag-op", keyfile(tmp_path, content))
    assert f"--operator-key-file is {word}; nothing sent" in err


def test_a_flag_key_file_that_is_missing_exits_2(tmp_path, capsys):
    assert "--operator-key-file is unreadable (FileNotFoundError); nothing sent" in refuses(
        capsys, "flag-op", str(tmp_path / "absent"))


def test_a_utf8_bom_and_trailing_newlines_are_stripped(tmp_path):
    assert cli.operator_pair("op", keyfile(tmp_path, b"\xef\xbb\xbf" + KEY.encode() + b"\r\n\n")) == ("op", KEY)


def test_a_key_file_of_exactly_4096_bytes_is_accepted_and_one_more_is_not(tmp_path, capsys):
    exact = keyfile(tmp_path, ("a" * 256) + "\n" * (4096 - 256))
    assert cli.operator_pair("op", exact) == ("op", "a" * 256)
    refuses(capsys, "op", keyfile(tmp_path, ("a" * 256) + "\n" * (4097 - 256), "big"))


# -- id and key go together -----------------------------------------------------------------------------------------

def test_an_id_flag_without_any_key_exits_2(capsys):
    assert "go together; nothing sent" in refuses(capsys, "flag-op", None)


def test_a_key_file_flag_without_an_id_exits_2(tmp_path, capsys):
    assert "go together; nothing sent" in refuses(capsys, None, keyfile(tmp_path, KEY))


def test_an_empty_id_flag_exits_2(tmp_path, capsys):
    assert "go together; nothing sent" in refuses(capsys, "  ", keyfile(tmp_path, KEY))


# -- shape of the pair ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["has space", "semi;colon", "Ã©", "a" * 65, "sl/ash", "new\nline"],
                         ids=["space", "semicolon", "non-ascii", "65-chars", "slash", "newline"])
def test_an_invalid_operator_id_exits_2(tmp_path, capsys, bad):
    err = refuses(capsys, bad, keyfile(tmp_path, KEY))
    assert "the operator id is not a valid operator id; nothing sent" in err


@pytest.mark.parametrize("good", ["a", "svc-1", "don@spin.example", "a.b_c-d", "x" * 64])
def test_a_valid_operator_id_is_accepted(tmp_path, good):
    assert cli.operator_pair(good, keyfile(tmp_path, KEY)) == (good, KEY)


@pytest.mark.parametrize("bad", ["two words", "semi;colon", "Ã©-key", "k" * 257, "tab\tinside"],
                         ids=["space", "semicolon", "non-ascii", "257-chars", "tab"])
def test_an_invalid_env_key_exits_2_saying_the_value_is_not_shown(monkeypatch, capsys, bad):
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", bad)
    err = refuses(capsys, None, None)
    assert "value not shown" in err and bad not in err


def test_a_padded_env_id_is_stripped(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR", "  env-op \n")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair(None, None) == ("env-op", ENV_KEY)


def test_the_env_key_alone_without_an_id_is_none_not_an_error(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    assert cli.operator_pair(None, None) is None
