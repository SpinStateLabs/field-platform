"""S6-16: UsageCursor.set promises a restart never re-posts a delta the governor already has. The
bytes must be on disk before the rename (fsync before os.replace), and a failed write or replace must
not leave a tmp-<pid>-<tid> file behind."""

from __future__ import annotations

import os

import pytest

from claude_approver.core import USAGE_FIELDS, UsageCursor

SNAP = {k: i + 1 for i, k in enumerate(USAGE_FIELDS)}


def _tmp_files(path):
    return [p.name for p in path.parent.iterdir() if ".tmp-" in p.name]


def test_the_file_is_fsynced_before_it_is_renamed(tmp_path, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    cur = UsageCursor(tmp_path / "usage-cursor.json")
    cur.set("sesn_1", SNAP)
    assert order[:2] == ["fsync", "replace"]


def test_the_cursor_after_set_equals_the_argument_and_survives_a_reload(tmp_path):
    path = tmp_path / "sub" / "usage-cursor.json"
    cur = UsageCursor(path)
    cur.set("sesn_1", SNAP)
    assert cur.get("sesn_1") == SNAP
    again = UsageCursor(path)
    again.load()
    assert again.error is None and again.get("sesn_1") == SNAP
    assert _tmp_files(path) == []


def test_a_failing_replace_leaves_no_tmp_file_and_memory_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "usage-cursor.json"
    cur = UsageCursor(path)
    cur.set("sesn_1", SNAP)

    def boom(a, b):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        cur.set("sesn_2", SNAP)
    assert _tmp_files(path) == []
    assert "sesn_2" not in cur.data


def test_a_failing_fsync_leaves_no_tmp_file(tmp_path, monkeypatch):
    path = tmp_path / "usage-cursor.json"
    cur = UsageCursor(path)

    def boom(fd):
        raise OSError("io error")
    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        cur.set("sesn_1", SNAP)
    assert _tmp_files(path) == [] and not path.exists() and cur.data == {}
