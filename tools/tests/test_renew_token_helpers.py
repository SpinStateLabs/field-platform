"""S8-30 — direct pins for renew_token's tail_lines, split_command, http_detail, clause_of and read_secret,
which no test named. Current behaviour only; quirks are noted where they are pinned, not changed."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import renew_token  # noqa: E402

SECRET = "SECRET-BODY-TEXT-MUST-NOT-LEAK"


# --- tail_lines (a leak control: a cut line is dropped whole, a secret may straddle the cut) ----------

@pytest.fixture()
def small_window(monkeypatch):
    monkeypatch.setattr(renew_token, "VERIFY_OUTPUT_MAX", 10)
    return 10


def tail(data: bytes) -> bytes:
    return renew_token.tail_lines(io.BytesIO(data), len(data))


def test_output_within_the_window_is_returned_whole(small_window):
    assert tail(b"") == b""
    assert tail(b"0123456789") == b"0123456789"          # size == max
    assert tail(b"abc\ndef") == b"abc\ndef"
    assert tail(b"a\r\nb") == b"a\r\nb"


def test_a_line_the_window_cuts_is_dropped_whole(small_window):
    # size 19: the window's first line "BBBBB..." starts before the window, so it is dropped
    assert tail(b"AAAA\nBBBBBBBBB\nCCCC") == b"CCCC"


def test_a_break_exactly_on_the_byte_before_the_window_keeps_the_first_window_line(small_window):
    data = b"AAAAA\nBBBBBBBBBB"                           # 16 bytes; the byte before the window is \n
    assert tail(data) == b"BBBBBBBBBB"


def test_a_window_with_no_break_is_empty(small_window):
    """The secret-straddles-the-cut guarantee: with no line start inside the window nothing is shown."""
    assert tail(b"x" * 24) == b""
    assert tail(b"x" * 11) == b""


def test_carriage_returns_are_breaks_too(small_window):
    assert tail(b"AAAAAAAAAAAA\rBBBB") == b"BBBB"
    assert tail(b"AAAAAAAAAAAA\r\nBBBB") == b"\nBBBB"     # QUIRK pinned: the \n of a \r\n stays on the front
    assert tail(b"AAAAAAAAAA\rBBBBBBBBB\r\nCC") == b"\nCC"


def test_the_secret_never_survives_a_cut_that_splits_it(small_window):
    data = b"prefix SECRETVALUE suffix\nlast"
    out = tail(data)
    assert b"SECRET" not in out and b"VALUE" not in out
    assert out == b"last"


def test_the_real_limit_is_used_by_default():
    big = b"line\n" * 50_000
    out = renew_token.tail_lines(io.BytesIO(big), len(big))
    assert len(out) <= renew_token.VERIFY_OUTPUT_MAX and out.startswith(b"line\n")


# --- split_command -----------------------------------------------------------------------------------

def test_split_command_posix_quoting_and_backslashes(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(renew_token.os, "name", "posix")                      # the POSIX branch, whatever the host
        assert renew_token.split_command('a "b c" d\\ e') == ["a", "b c", "d e"]
        assert renew_token.split_command("a 'b c'") == ["a", "b c"]
        assert renew_token.split_command('a "" b') == ["a", "", "b"]   # an empty token is kept
        assert renew_token.split_command("") == []
        assert renew_token.split_command("a\\b") == ["ab"]              # POSIX: a backslash escapes


@pytest.mark.parametrize("cmd", ['a "b', "a 'b", 'a "b c'])
def test_split_command_unbalanced_quotes_raise_value_error(cmd):
    with pytest.raises(ValueError):
        renew_token.split_command(cmd)


def test_split_command_windows_branch_keeps_backslashes_and_strips_outer_quotes(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(renew_token.os, "name", "nt")
        assert renew_token.split_command(r'"C:\Program Files\x.exe" arg') == [r"C:\Program Files\x.exe", "arg"]
        assert renew_token.split_command(r"C:\tools\x.exe a\b") == [r"C:\tools\x.exe", r"a\b"]
        assert renew_token.split_command('a "" b') == ["a", "", "b"]
        assert renew_token.split_command('""') == [""]                  # an empty quoted token is kept
        with pytest.raises(ValueError):
            renew_token.split_command('"')                              # a lone quote is unbalanced


def test_split_command_windows_branch_unbalanced_quote_raises(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(renew_token.os, "name", "nt")
        with pytest.raises(ValueError):
            renew_token.split_command('a "b')


# --- http_detail / clause_of -------------------------------------------------------------------------

def test_http_detail_for_a_transport_error_names_only_the_type():
    assert renew_token.http_detail(0, {"transport_error": "URLError"}) == "transport error URLError"
    assert renew_token.http_detail(0, {}) == "transport error ?"
    assert renew_token.http_detail(0, "oops") == "HTTP 0"


@pytest.mark.parametrize("body, want", [
    ({"detail": {"clause_id": "D.grantor"}}, "HTTP 403 D.grantor"),
    ({"detail": {"clause_id": "E.spend_cap"}}, "HTTP 403 E.spend_cap"),
    ({"detail": {"clause_id": "d.grantor"}}, "HTTP 403"),               # shape: upper letter, dot, lower
    ({"detail": {"clause_id": "D.Grantor"}}, "HTTP 403"),
    ({"detail": {"clause_id": "DD.grantor"}}, "HTTP 403"),
    ({"detail": {"clause_id": "D."}}, "HTTP 403"),
    ({"detail": {"clause_id": "D." + "a" * 41}}, "HTTP 403"),            # 41 > the 40 limit
    ({"detail": {"clause_id": "D." + "a" * 40}}, "HTTP 403 D." + "a" * 40),
    ({"detail": {"clause_id": "D.grantor\n"}}, "HTTP 403"),              # fullmatch: no trailing newline
    ({"detail": {"clause_id": "D.grantor extra"}}, "HTTP 403"),
    ({"detail": {"clause_id": 5}}, "HTTP 403"),
    ({"detail": {"clause_id": None}}, "HTTP 403"),
    ({"detail": SECRET}, "HTTP 403"),
    ({"detail": [SECRET]}, "HTTP 403"),
    ({"detail": None}, "HTTP 403"),
    ({}, "HTTP 403"),
    (SECRET, "HTTP 403"),
    ([SECRET], "HTTP 403"),
    (None, "HTTP 403"),
])
def test_http_detail_and_clause_of_never_echo_a_body(body, want):
    out = renew_token.http_detail(403, body)
    assert out == want and SECRET not in out
    clause = renew_token.clause_of(body)
    assert clause == (want.split(" ", 2)[2] if want.count(" ") == 2 else None)


def test_clause_of_returns_only_a_well_formed_id():
    assert renew_token.clause_of({"detail": {"clause_id": "D.grantor"}}) == "D.grantor"
    assert renew_token.clause_of({"detail": {"clause_id": "bad id"}}) is None
    assert renew_token.clause_of(None) is None


# --- read_secret -------------------------------------------------------------------------------------

def write(tmp_path, raw: bytes) -> str:
    p = tmp_path / "secret"
    p.write_bytes(raw)
    return str(p)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)


def test_a_file_value_is_stripped(tmp_path):
    assert renew_token.read_secret(write(tmp_path, b"  s3cret-value \r\n")) == "s3cret-value"


@pytest.mark.parametrize("raw, message", [
    (b"", "is empty"), (b"   \n\t", "is empty"),
    ("sécret".encode(), "whitespace, control or non-ASCII"),
    (b"two words", "whitespace, control or non-ASCII"),
    (b"a\x01b", "whitespace, control or non-ASCII"),
    (b"a\tb", "whitespace, control or non-ASCII"),
    (b"\xef\xbb\xbfs3cret", "whitespace, control or non-ASCII"),   # a BOM is refused here (no utf-8-sig)
    (b"\xff\xfebad", "not readable"),                              # not UTF-8
])
def test_a_bad_file_is_refused_without_showing_the_value(tmp_path, raw, message):
    with pytest.raises(renew_token.Refused) as info:
        renew_token.read_secret(write(tmp_path, raw))
    assert message in str(info.value) and "s3cret" not in str(info.value)


def test_a_missing_file_or_directory_is_not_readable(tmp_path):
    with pytest.raises(renew_token.Refused, match="not readable"):
        renew_token.read_secret(str(tmp_path / "nope"))
    with pytest.raises(renew_token.Refused, match="not readable"):
        renew_token.read_secret(str(tmp_path))


def test_the_environment_is_the_fallback(monkeypatch):
    assert renew_token.read_secret(None) is None
    monkeypatch.setenv("FIELD_SHARED_SECRET", "env-secret")
    assert renew_token.read_secret(None) == "env-secret"
    assert renew_token.read_secret("") == "env-secret"                 # blank --secret-file means "not given"


def test_the_environment_value_is_not_stripped_and_is_checked(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", " env-secret ")
    with pytest.raises(renew_token.Refused):
        renew_token.read_secret(None)
    monkeypatch.setenv("FIELD_SHARED_SECRET", "sécret")
    with pytest.raises(renew_token.Refused):
        renew_token.read_secret(None)
    monkeypatch.setenv("FIELD_SHARED_SECRET", "")
    assert renew_token.read_secret(None) is None


def test_a_file_wins_over_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "env-secret")
    assert renew_token.read_secret(write(tmp_path, b"file-secret\n")) == "file-secret"
