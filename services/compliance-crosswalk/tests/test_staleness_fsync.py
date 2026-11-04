"""S3-24: StaleStore._persist wrote a temp file and os.replace()d it with no flush/fsync, so after a power loss the
replaced file could be empty or partial; the store then fails to load, and a lost write silently reopens the
evidence-pack gate that a stale flag closes. The temp file is now flushed and fsynced BEFORE the replace, and the
directory is fsynced after it (best effort). A failing fsync leaves the old file intact and no temp file behind."""

from __future__ import annotations

import json
import os

import pytest

from compliance_crosswalk.staleness import StaleStore


@pytest.fixture()
def events(monkeypatch):
    """Record os.fsync / os.replace in order; for an fsync, the inode of the file it was called on."""
    log: list[tuple] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        log.append(("fsync", os.fstat(fd).st_ino))
        return real_fsync(fd)

    def replace(src, dst):
        log.append(("replace", str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    return log


def _kinds(log):
    return [e[0] for e in log]


@pytest.mark.parametrize("op", ["mark", "clear"])
def test_the_temp_file_is_fsynced_before_the_replace_and_the_directory_after(tmp_path, events, op):
    path = tmp_path / "flags.json"
    s = StaleStore(path)
    s.mark("osfi-e23", "revision opened")
    events.clear()
    if op == "mark":
        s.mark("eu-ai-act", "amendment published")
    else:
        s.clear("osfi-e23", "D. Hagell")
    kinds = _kinds(events)
    assert kinds[:2] == ["fsync", "replace"], kinds                       # the file's fsync comes first
    first_fsync_inode = events[0][1]
    assert first_fsync_inode == path.stat().st_ino                         # ...on the very file that was renamed in
    assert kinds[-1] == "fsync" and len(kinds) == 3                        # then the directory, after the replace
    assert events[2][1] != first_fsync_inode


def test_the_persisted_content_is_unchanged(tmp_path):
    path = tmp_path / "flags.json"
    s = StaleStore(path)
    s.mark("osfi-e23", "revision opened")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"corpus_version", "active", "history", "sources", "last_check"}
    assert list(data["active"]) == ["osfi-e23"] and path.read_text(encoding="utf-8").endswith("\n")
    assert StaleStore(path).active() == s.active()


def test_a_failing_file_fsync_leaves_the_old_file_intact_and_no_temp_behind(tmp_path, monkeypatch):
    path = tmp_path / "flags.json"
    s = StaleStore(path)
    s.mark("osfi-e23", "revision opened")
    before = path.read_bytes()

    def boom(fd):
        raise OSError("disk fault")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError, match="disk fault"):
        s.mark("eu-ai-act", "amendment published")
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")) == []


def test_a_failing_directory_fsync_does_not_fail_the_write(tmp_path, monkeypatch):
    path = tmp_path / "flags.json"
    s = StaleStore(path)
    real = os.fsync
    calls = []

    def fsync(fd):
        calls.append(fd)
        if len(calls) == 2:                                   # the second call is the directory's
            raise OSError("directories cannot be fsynced here")
        return real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    s.mark("osfi-e23", "revision opened")
    assert len(calls) == 2
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]


def test_a_failing_replace_still_cleans_up_the_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "flags.json"
    s = StaleStore(path)
    s.mark("osfi-e23", "revision opened")

    def boom(src, dst):
        raise OSError("rename fault")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="rename fault"):
        s.mark("eu-ai-act", "amendment published")
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")) == []
