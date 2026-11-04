"""S7-32 — estate_kill_watcher: a --secret-file written by Windows PowerShell 5.1 (UTF-8 BOM) is read like
estate_probe, renew_token and provision_ssl_agents read theirs, and a kill can never replace a sentinel a
human created between the existence check and the create."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_kill_watcher as w  # noqa: E402

BOM = b"\xef\xbb\xbf"


def secret_file(tmp_path, raw: bytes) -> str:
    p = tmp_path / "secret"
    p.write_bytes(raw)
    return str(p)


# --- read_secret -------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [BOM + b"s3cret-value", BOM + b"s3cret-value\r\n", BOM + b"  s3cret-value \n"])
def test_a_bom_secret_file_is_accepted_and_stripped(tmp_path, raw):
    assert w.read_secret(secret_file(tmp_path, raw)) == "s3cret-value"


def test_a_plain_secret_file_is_unchanged(tmp_path):
    assert w.read_secret(secret_file(tmp_path, b"s3cret-value\n")) == "s3cret-value"


@pytest.mark.parametrize("raw", [BOM, BOM + b"\n", b"", b"  \n"])
def test_a_bom_only_or_blank_file_is_refused_as_empty(tmp_path, raw):
    with pytest.raises(w.Refused, match="is empty"):
        w.read_secret(secret_file(tmp_path, raw))


@pytest.mark.parametrize("raw", [BOM + "sécret".encode(), BOM + b"two words", BOM + b"a\x01b", b"a\tb"])
def test_every_other_refusal_is_kept(tmp_path, raw):
    with pytest.raises(w.Refused, match="whitespace, control or non-ASCII"):
        w.read_secret(secret_file(tmp_path, raw))


def test_a_non_utf8_or_missing_file_is_unreadable(tmp_path):
    with pytest.raises(w.Refused, match="not readable"):
        w.read_secret(secret_file(tmp_path, b"\xff\xfe\x00bad"))
    with pytest.raises(w.Refused, match="not readable"):
        w.read_secret(str(tmp_path / "nope"))


# --- apply: the human-sentinel race ------------------------------------------------------------------

HUMAN = b"a human wrote this halt\n"


def test_a_kill_creates_the_sentinel_with_the_marker_and_leaves_no_temp(tmp_path):
    s = tmp_path / "SENTINEL"
    assert w.apply(str(s), True, "agent-1", "killed") == "killed: sentinel created"
    first = s.read_text(encoding="utf-8").splitlines()[0]
    assert first == w.MARKER
    assert [p.name for p in tmp_path.iterdir()] == ["SENTINEL"]


def test_a_human_sentinel_that_appears_between_the_check_and_the_create_survives(tmp_path, monkeypatch):
    s = tmp_path / "SENTINEL"
    s.write_bytes(HUMAN)
    monkeypatch.setattr(w.os.path, "lexists", lambda p: False)  # the check ran before the human's file existed
    assert w.apply(str(s), True, "agent-1", "killed") == "killed: sentinel already present"
    assert s.read_bytes() == HUMAN
    assert [p.name for p in tmp_path.iterdir()] == ["SENTINEL"]  # the temp file is gone


def test_the_revive_still_leaves_a_human_sentinel_in_place(tmp_path):
    s = tmp_path / "SENTINEL"
    s.write_bytes(HUMAN)
    assert w.apply(str(s), False, "agent-1", "alive") == "alive: sentinel is not the watcher's, left in place"
    assert s.read_bytes() == HUMAN


def test_a_watcher_sentinel_is_still_revived(tmp_path):
    s = tmp_path / "SENTINEL"
    w.apply(str(s), True, "agent-1", "killed")
    assert w.apply(str(s), False, "agent-1", "alive") == "alive: sentinel removed (revive)"
    assert not s.exists()


def test_an_existing_sentinel_is_already_present_without_the_race(tmp_path):
    s = tmp_path / "SENTINEL"
    s.write_bytes(HUMAN)
    assert w.apply(str(s), True, "agent-1", "killed") == "killed: sentinel already present"
    assert s.read_bytes() == HUMAN


def test_without_hard_links_an_exclusive_create_still_refuses_to_replace(tmp_path, monkeypatch):
    def no_link(src, dst, **k):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(w.os, "link", no_link)
    s = tmp_path / "SENTINEL"
    assert w.apply(str(s), True, "agent-1", "killed") == "killed: sentinel created"
    assert s.read_text(encoding="utf-8").splitlines()[0] == w.MARKER
    s.write_bytes(HUMAN)
    monkeypatch.setattr(w.os.path, "lexists", lambda p: False)
    assert w.apply(str(s), True, "agent-1", "killed") == "killed: sentinel already present"
    assert s.read_bytes() == HUMAN
    assert [p.name for p in tmp_path.iterdir()] == ["SENTINEL"]


def test_a_symlink_sentinel_is_still_refused(tmp_path):
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "SENTINEL"
    os.symlink(target, link)
    with pytest.raises(w.Refused):
        w.apply(str(link), True, "agent-1", "killed")
