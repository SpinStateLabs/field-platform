"""C-136 (reviewer R-13 F-R13-1, store.py `_rename_with_retry`): the rename retry loop is pinned.

A reader holding a plain handle makes `os.rename` raise PermissionError (Windows WinError 32); the
loop retries RENAME_RETRIES times and then re-raises the PermissionError.
"""

from __future__ import annotations

import os

import pytest

from sealed_ledger import store as store_mod
from sealed_ledger.store import LedgerStore, RotationRefused


def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "RENAME_RETRY_DELAY_S", 0)
    return LedgerStore(tmp_path / "e.jsonl")


def _flaky_rename(monkeypatch, failures):
    calls = []
    real = os.rename

    def rename(src, dst):
        calls.append((src, dst))
        if len(calls) <= failures:
            raise PermissionError("WinError 32")
        real(src, dst)

    monkeypatch.setattr(store_mod.os, "rename", rename)
    return calls


def test_rename_retries_a_transient_permission_error_then_succeeds(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    calls = _flaky_rename(monkeypatch, LedgerStore.RENAME_RETRIES - 1)
    assert s._rename_with_retry(src, dst) == LedgerStore.RENAME_RETRIES
    assert len(calls) == LedgerStore.RENAME_RETRIES
    assert dst.read_text() == "x" and not src.exists()


def test_rename_first_try_returns_attempt_one(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    assert s._rename_with_retry(src, dst) == 1


def test_rename_gives_up_with_the_permission_error_after_exactly_n_attempts(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    calls = _flaky_rename(monkeypatch, 10**6)
    with pytest.raises(PermissionError):  # not AssertionError("unreachable")
        s._rename_with_retry(src, dst)
    assert len(calls) == LedgerStore.RENAME_RETRIES
    assert src.exists() and not dst.exists()


def test_rename_refuses_an_existing_destination_without_trying(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    dst.write_text("y")
    calls = _flaky_rename(monkeypatch, 0)
    with pytest.raises(RotationRefused):
        s._rename_with_retry(src, dst)
    assert calls == [] and dst.read_text() == "y"


def test_rename_sleeps_the_configured_delay_between_attempts_only(tmp_path, monkeypatch):
    # C-153 (reviewer C-146 F-C146-1): one sleep of RENAME_RETRY_DELAY_S after each failed
    # attempt but the last; no sleep on success or before giving up.
    s = _store(tmp_path, monkeypatch)
    monkeypatch.setattr(LedgerStore, "RENAME_RETRY_DELAY_S", 0.25)
    sleeps = []
    monkeypatch.setattr(store_mod.time, "sleep", sleeps.append)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    _flaky_rename(monkeypatch, LedgerStore.RENAME_RETRIES - 1)
    assert s._rename_with_retry(src, dst) == LedgerStore.RENAME_RETRIES
    assert sleeps == [0.25] * (LedgerStore.RENAME_RETRIES - 1)
    sleeps.clear()
    src2, dst2 = tmp_path / "c", tmp_path / "d"
    src2.write_text("x")
    _flaky_rename(monkeypatch, 10**6)
    with pytest.raises(PermissionError):
        s._rename_with_retry(src2, dst2)
    assert sleeps == [0.25] * (LedgerStore.RENAME_RETRIES - 1)


def test_rename_does_not_retry_a_non_permission_oserror(tmp_path, monkeypatch):
    # C-153 (reviewer C-146 F-C146-2): only PermissionError is transient; anything else is raised
    # at once, after exactly one os.rename call.
    s = _store(tmp_path, monkeypatch)
    calls = []

    def rename(src, dst):
        calls.append((src, dst))
        raise FileNotFoundError("gone")

    monkeypatch.setattr(store_mod.os, "rename", rename)
    with pytest.raises(FileNotFoundError):
        s._rename_with_retry(tmp_path / "a", tmp_path / "b")
    assert len(calls) == 1
