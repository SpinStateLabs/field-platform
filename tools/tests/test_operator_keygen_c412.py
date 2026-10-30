"""C-412 (reviewer C-408 F-C408-1, -2, -4 on operator_keygen --add-to).

F-C408-1: the sentence "with --key-file the key file exists whenever the row does" was false in one window: an
interrupt after the registry rename removed the key file of a row that now exists. The key file is now removed only
when the run's key hash is not in the registry file. F-C408-2: a key file that cannot be opened (missing directory, no
permission, already there) is an `error:` exit, not a traceback. F-C408-4: the lock's file descriptor is closed."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402


def seed(tmp_path: Path) -> tuple[Path, bytes]:
    f = tmp_path / "operators.json"
    f.write_text(json.dumps([{"operator_id": "don", "key_sha256": "a" * 64, "status": "active",
                              "created_at": "2026-10-01T00:00:00+00:00", "scopes": ["*"], "names": []}]), encoding="utf-8")
    return f, f.read_bytes()


def ids(f: Path) -> list[str]:
    return [r["operator_id"] for r in json.loads(f.read_text(encoding="utf-8"))]


def run(f: Path, kf: Path, op: str = "new") -> int:
    return kg.main(["--operator-id", op, "--add-to", str(f), "--key-file", str(kf)])


# --- F-C408-1: an interrupt after the registry was replaced keeps the key file -----------------------------------


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), RuntimeError("late"), SystemExit("late")])
def test_a_failure_after_the_registry_was_replaced_keeps_the_key_file_of_the_row_that_exists(tmp_path, monkeypatch, exc):
    f, _ = seed(tmp_path)
    kf = tmp_path / "new.key"
    real = kg.write_registry

    def write_then_fail(path, out):
        real(path, out)                                      # the rename landed
        raise exc

    monkeypatch.setattr(kg, "write_registry", write_then_fail)
    with pytest.raises(type(exc)):
        run(f, kf)
    assert "new" in ids(f)
    assert kf.exists() and kf.read_text(encoding="utf-8").startswith("fok_")      # the row has its key


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), RuntimeError("early"), SystemExit("early")])
def test_a_failure_before_the_registry_was_replaced_removes_the_key_file(tmp_path, monkeypatch, exc):
    f, before = seed(tmp_path)
    kf = tmp_path / "new.key"

    def fail(path, out):
        raise exc

    monkeypatch.setattr(kg, "write_registry", fail)
    with pytest.raises(type(exc)):
        run(f, kf)
    assert not kf.exists() and f.read_bytes() == before


def test_a_registry_changed_by_someone_else_still_removes_the_key_file(tmp_path, monkeypatch):
    """Our hash is absent from the file the other writer produced: nothing of ours landed, the key file goes."""
    f, _ = seed(tmp_path)
    kf = tmp_path / "new.key"
    real = kg._snapshot
    calls = {"n": 0}

    def edited_after_the_first_read(path):
        calls["n"] += 1
        if calls["n"] == 2:                                  # the compare inside commit_registry: the file moved on
            f.write_text(f.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return real(path)

    monkeypatch.setattr(kg, "_snapshot", edited_after_the_first_read)
    with pytest.raises(SystemExit):
        run(f, kf)
    assert "new" not in ids(f) and not kf.exists()


def test_hash_registered_reads_the_file_and_an_unreadable_one_is_not_registered(tmp_path):
    f = tmp_path / "ops.json"
    f.write_text('[{"key_sha256": "' + "b" * 64 + '"}]', encoding="utf-8")
    assert kg._hash_registered(f, "b" * 64) is True
    assert kg._hash_registered(f, "c" * 64) is False
    assert kg._hash_registered(tmp_path / "missing.json", "b" * 64) is False


# --- F-C408-2: a key file that cannot be opened is an error: exit -------------------------------------------------


def test_a_key_file_in_a_missing_directory_is_an_error_exit_and_nothing_is_registered(tmp_path, capsys):
    f, before = seed(tmp_path)
    kf = tmp_path / "no-such-dir" / "new.key"
    with pytest.raises(SystemExit) as e:
        run(f, kf)
    assert str(e.value).startswith("error: cannot write the key file ") and "fok_" not in str(e.value)
    assert f.read_bytes() == before and not kf.parent.exists()
    assert "fok_" not in capsys.readouterr().out


def test_an_existing_key_file_is_an_error_exit_left_untouched_and_nothing_is_registered(tmp_path):
    f, before = seed(tmp_path)
    kf = tmp_path / "new.key"
    kf.write_text("PRE-EXISTING", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        run(f, kf)
    assert "already exists" in str(e.value) and str(kf) in str(e.value)
    assert kf.read_text(encoding="utf-8") == "PRE-EXISTING" and f.read_bytes() == before


def test_a_key_file_that_cannot_be_opened_for_permission_is_an_error_exit(tmp_path, monkeypatch):
    f, before = seed(tmp_path)
    kf = tmp_path / "new.key"
    real_open = os.open

    def deny(path, flags, *a, **k):
        if str(path) == str(kf):
            raise PermissionError(13, "Permission denied")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(kg.os, "open", deny)
    with pytest.raises(SystemExit) as e:
        run(f, kf)
    assert str(e.value) == f"error: cannot write the key file {kf}: Permission denied"
    assert f.read_bytes() == before


def test_a_failed_open_never_removes_a_file_it_did_not_create(tmp_path):
    kf = tmp_path / "new.key"
    kf.write_text("PRE-EXISTING", encoding="utf-8")
    with pytest.raises(SystemExit):
        kg._write_key_file(str(kf), "fok_x")
    assert kf.exists()


# --- F-C408-4: the lock's descriptor is closed ----------------------------------------------------------------------


def _record_fds(monkeypatch):
    opened, closed = [], []
    real_open, real_close = os.open, os.close

    def op(path, *a, **k):
        fd = real_open(path, *a, **k)
        if str(path).endswith(".lock"):
            opened.append(fd)
        return fd

    def cl(fd):
        closed.append(fd)
        return real_close(fd)

    monkeypatch.setattr(kg.os, "open", op)
    monkeypatch.setattr(kg.os, "close", cl)
    return opened, closed


def test_the_lock_descriptor_is_closed_after_a_clean_run(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)
    opened, closed = _record_fds(monkeypatch)
    with kg.registry_lock(f):
        assert len(opened) == 1 and opened[0] not in closed
    assert opened[0] in closed


def test_the_lock_descriptor_is_closed_when_the_body_fails(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)
    opened, closed = _record_fds(monkeypatch)
    with pytest.raises(RuntimeError):
        with kg.registry_lock(f):
            raise RuntimeError("body")
    assert opened and opened[0] in closed


def test_the_lock_descriptor_is_closed_when_the_lock_times_out(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)
    opened, closed = _record_fds(monkeypatch)
    monkeypatch.setattr(kg, "_try_lock", lambda fd: False)
    with pytest.raises(SystemExit):
        with kg.registry_lock(f, timeout=0.05):
            pass
    assert opened and opened[0] in closed


def test_the_docstring_states_the_new_key_file_promise_and_not_the_old_one():
    doc = kg.__doc__
    assert "With --key-file the key file exists whenever the row does" not in doc
    for phrase in ("removed whenever the row was NOT written", "the key file is kept"):
        assert phrase in doc, phrase
