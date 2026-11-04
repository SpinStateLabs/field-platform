"""S2-6: an undecodable, Infinity or negative usage cursor disables posting; it never restarts usage from zero.

`UsageCursor.load` set `_loaded` before parsing and caught only (ValueError, TypeError). Invalid UTF-8 (a
UnicodeDecodeError is neither caught nor an OSError) and `Infinity` (int(inf) is an OverflowError) escaped, tick 1
counted a tick error, and tick 2 saw an empty, error-free cursor and re-posted every session's whole history.
SPEC.md says a corrupt cursor disables posting rather than starting from zero. A negative or bool counter is
corrupt too: a negative one would make the next delta larger than the real usage, and a bool is not a counter."""

import pytest

from approver_fakes import CONSOLE_AGENT, usage

SID = "sesn_u1"

CORRUPT = "usage cursor is corrupt"


def _write(tmp_path, content):
    cursor = tmp_path / "data" / "claude-approver" / "usage-cursor.json"
    cursor.parent.mkdir(parents=True)
    if isinstance(content, bytes):
        cursor.write_bytes(content)
    else:
        cursor.write_text(content, encoding="utf-8")


@pytest.mark.parametrize("content", [
    b"\xff\xfe\x00not utf-8 \x80\x81",
    '{"%s": {"input_tokens": Infinity}}' % SID,
    '{"%s": {"input_tokens": -5}}' % SID,
    '{"%s": {"input_tokens": true}}' % SID,
], ids=["invalid-utf8", "infinity", "negative", "bool"])
def test_a_corrupt_cursor_posts_nothing_on_either_tick(content, console, field, make_approver, mapped, tmp_path):
    _write(tmp_path, content)
    console.add_session(SID, CONSOLE_AGENT, use=usage(10, 1))
    a = make_approver()
    a.tick()
    assert field.usage_posts() == []
    a.tick()
    assert field.usage_posts() == []
    assert a.stats()["usage_cursor_error"] == CORRUPT
    assert a.stats()["tick_errors"] == 0
