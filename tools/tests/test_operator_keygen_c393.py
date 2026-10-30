"""C-393 (reviewer C-354 F-C354-1..5 on operator_keygen --add-to): the read-modify-write is serialised, and a failed
registration leaves no key on ANY failure.

F-C354-1: two simultaneous runs against one operators file lost an update 47 times in 200 (both exit 0, both print
"registered", one row in the file). The whole read-modify-write now runs under an exclusive lock on
`<operators file>.lock`, re-reading the file under it. F-C354-2: the key file is removed on any failure, Ctrl-C and an
unexpected error included. F-C354-3: the recovery for a key registered but never shown is documented. F-C354-4: a
failed key-file write is an `error:` exit that removes what it created. F-C354-5: the byte compare cannot see a
reverted edit; the lock makes that moot (the compare stays as a second layer)."""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402


def seed(tmp_path: Path) -> tuple[Path, bytes]:
    f = tmp_path / "operators.json"
    sha = "a" * 64
    f.write_text(json.dumps([{"operator_id": "don", "key_sha256": sha, "status": "active",
                              "created_at": "2026-10-01T00:00:00+00:00", "scopes": ["*"], "names": []}]), encoding="utf-8")
    return f, f.read_bytes()


def ids(f: Path) -> list[str]:
    return [r["operator_id"] for r in json.loads(f.read_text(encoding="utf-8"))]


# --- F-C354-1: the lock --------------------------------------------------------------------------------------


def test_two_writers_that_overlap_inside_the_write_both_register(tmp_path, monkeypatch):
    """Deterministic version of the reviewer's race: writer A is paused inside its registry write (after its compare
    passed, before the rename) until writer B has finished. Without the lock B finishes first and A's rename
    overwrites B's row (a lost update); with it B waits, A completes, and B then re-reads and adds its own row."""
    f, _ = seed(tmp_path)
    real_write = kg.write_registry
    a_inside, b_done = threading.Event(), threading.Event()
    first = {"taken": False}

    def slow_first_write(path, out):
        if not first["taken"]:
            first["taken"] = True
            a_inside.set()
            b_done.wait(timeout=1.5)               # without the lock B completes while A waits here
        real_write(path, out)

    monkeypatch.setattr(kg, "write_registry", slow_first_write)
    results: dict[str, object] = {}

    def run(name):
        try:
            results[name] = kg.main(["--operator-id", name, "--add-to", str(f), "--key-file", str(tmp_path / f"{name}.key")])
        except SystemExit as exc:
            results[name] = exc.code

    ta = threading.Thread(target=run, args=("writer-a",))
    ta.start()
    assert a_inside.wait(timeout=5)
    tb = threading.Thread(target=lambda: (run("writer-b"), b_done.set()))
    tb.start()
    ta.join(timeout=15)
    tb.join(timeout=15)
    assert results == {"writer-a": 0, "writer-b": 0}, results
    assert sorted(ids(f)) == ["don", "writer-a", "writer-b"]
    assert (tmp_path / "writer-a.key").exists() and (tmp_path / "writer-b.key").exists()


@pytest.mark.skipif(sys.platform == "win32" and os.environ.get("CI") != "true", reason="slow multi-process stress; run in CI")
def test_two_real_processes_started_together_never_lose_an_update(tmp_path):
    """The reviewer's 200-trial probe, smaller: both processes succeed and the file holds both rows, every trial."""
    for trial in range(25):
        f, _ = seed(tmp_path)
        procs = [subprocess.Popen([sys.executable, str(TOOLS / "operator_keygen.py"), "--operator-id", f"w{trial}-{n}",
                                   "--add-to", str(f)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for n in (1, 2)]
        codes = [p.wait(timeout=60) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        assert codes == [0, 0], (trial, codes)
        assert sorted(ids(f)) == ["don", f"w{trial}-1", f"w{trial}-2"], trial


def test_the_lock_is_held_from_the_read_to_the_commit_and_released_after(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)
    events: list[str] = []
    real_try, real_unlock = kg._try_lock, kg._unlock
    monkeypatch.setattr(kg, "_try_lock", lambda fd: (real_try(fd) and (events.append("lock") or True)))
    monkeypatch.setattr(kg, "_unlock", lambda fd: (events.append("unlock"), real_unlock(fd))[1])
    real_snapshot, real_prepare, real_commit = kg._snapshot, kg.prepare_entry, kg.commit_registry
    monkeypatch.setattr(kg, "_snapshot", lambda p: (events.append("snapshot"), real_snapshot(p))[1])
    monkeypatch.setattr(kg, "prepare_entry", lambda *a, **k: (events.append("prepare"), real_prepare(*a, **k))[1])

    def commit(*a, **k):
        events.append("commit")
        return real_commit(*a, **k)

    monkeypatch.setattr(kg, "commit_registry", commit)
    assert kg.main(["--operator-id", "new", "--add-to", str(f)]) == 0
    first = events.index("lock")
    # the second "snapshot" is the compare inside commit_registry: still under the lock, before the unlock
    assert events[first:first + 6] == ["lock", "snapshot", "prepare", "commit", "snapshot", "unlock"]
    assert events.count("lock") == 1 and events.count("unlock") == 1


def test_the_lock_is_released_when_the_run_fails(tmp_path):
    f, _ = seed(tmp_path)
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "don", "--add-to", str(f)])        # a duplicate id: refused inside the lock
    with kg.registry_lock(f, timeout=0.5):                           # obtainable again at once
        pass


def test_a_second_holder_waits_until_the_first_releases(tmp_path):
    f, _ = seed(tmp_path)
    order: list[str] = []
    release = threading.Event()

    def holder():
        with kg.registry_lock(f):
            order.append("first-in")
            release.wait(timeout=5)
            order.append("first-out")

    t = threading.Thread(target=holder)
    t.start()
    while "first-in" not in order:
        threading.Event().wait(0.01)
    threading.Timer(0.3, release.set).start()
    with kg.registry_lock(f, timeout=5):
        order.append("second-in")
    t.join(timeout=5)
    assert order == ["first-in", "first-out", "second-in"]


def test_a_run_that_cannot_get_the_lock_writes_nothing_and_exits_with_an_error(tmp_path, monkeypatch, capsys):
    f, before = seed(tmp_path)
    monkeypatch.setattr(kg, "LOCK_TIMEOUT_S", 0.3)
    kf = tmp_path / "new.key"
    outcome: dict = {}

    def contender():
        try:
            kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)])
        except SystemExit as exc:
            outcome["exit"] = exc

    with kg.registry_lock(f):
        t = threading.Thread(target=contender, daemon=True)
        t.start()
        t.join(timeout=10)                       # a run that ignores its timeout would still be waiting here
        assert not t.is_alive(), "the contender did not give up at its timeout"
    e = outcome["exit"]
    assert "is being written by another operator_keygen" in str(e) and "nothing was written" in str(e)
    assert f.read_bytes() == before and not kf.exists()
    assert "fok_" not in capsys.readouterr().out


def test_the_timeout_default_is_thirty_seconds():
    assert kg.LOCK_TIMEOUT_S == 30.0


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_the_lock_file_is_beside_the_registry_mode_0600_and_never_deleted(tmp_path):
    f, _ = seed(tmp_path)
    kg.main(["--operator-id", "new", "--add-to", str(f)])
    lock = tmp_path / "operators.json.lock"
    assert lock.exists() and (lock.stat().st_mode & 0o777) == 0o600
    kg.main(["--operator-id", "newer", "--add-to", str(f)])
    assert lock.exists()


def test_check_and_a_plain_key_make_no_lock_file(tmp_path, capsys):
    f, _ = seed(tmp_path)
    assert kg.main(["--check", str(f)]) in (0, 1)
    kg.main([])                                                       # a bare key: nothing registered
    assert not (tmp_path / "operators.json.lock").exists()


def test_a_lock_file_that_cannot_be_created_is_an_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    f, before = seed(tmp_path)
    real_open = os.open

    def deny_lock(path, *a, **k):
        if str(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, "denied")
        return real_open(path, *a, **k)

    monkeypatch.setattr(kg.os, "open", deny_lock)
    kf = tmp_path / "new.key"
    with pytest.raises(SystemExit) as e:
        kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)])
    assert str(e.value).startswith("error: cannot write ") and "lock file" in str(e.value)
    assert f.read_bytes() == before and not kf.exists() and "fok_" not in capsys.readouterr().out


def test_a_try_lock_error_that_is_not_contention_is_raised(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)
    if os.name == "nt":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", lambda fd, mode, n: (_ for _ in ()).throw(OSError(errno.EIO, "io")))
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", lambda fd, op: (_ for _ in ()).throw(OSError(errno.EIO, "io")))
    with pytest.raises(OSError):
        with kg.registry_lock(f, timeout=0.2):
            pass


@pytest.mark.parametrize("code", [errno.EACCES, errno.EAGAIN])
def test_a_contention_errno_means_not_acquired(tmp_path, monkeypatch, code):
    f, _ = seed(tmp_path)
    if os.name == "nt":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", lambda fd, mode, n: (_ for _ in ()).throw(OSError(code, "held")))
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", lambda fd, op: (_ for _ in ()).throw(OSError(code, "held")))
    fd = os.open(tmp_path / "x.lock", os.O_RDWR | os.O_CREAT)
    try:
        assert kg._try_lock(fd) is False
    finally:
        os.close(fd)


# --- F-C354-2: any failure removes the key file ---------------------------------------------------------------


@pytest.mark.parametrize("exc", [KeyboardInterrupt, RuntimeError("boom"), SystemExit("error: x"), MemoryError()])
def test_any_failure_of_the_registry_commit_removes_the_key_file(tmp_path, monkeypatch, capsys, exc):
    f, before = seed(tmp_path)
    kf = tmp_path / "new.key"

    def fail(*a, **k):
        raise exc

    monkeypatch.setattr(kg, "commit_registry", fail)
    with pytest.raises(type(exc) if isinstance(exc, BaseException) else exc):
        kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)])
    assert not kf.exists() and f.read_bytes() == before
    assert "fok_" not in capsys.readouterr().out


@pytest.mark.parametrize("exc", [KeyboardInterrupt, RuntimeError("boom")])
def test_in_printed_mode_a_failed_commit_shows_no_key(tmp_path, monkeypatch, capsys, exc):
    f, before = seed(tmp_path)
    monkeypatch.setattr(kg, "commit_registry", lambda *a, **k: (_ for _ in ()).throw(exc))
    with pytest.raises(BaseException):
        kg.main(["--operator-id", "new", "--add-to", str(f)])
    assert f.read_bytes() == before and "fok_" not in capsys.readouterr().out


# --- F-C354-4: a failed key-file write ---------------------------------------------------------------------------


class _FullDisk:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, text):
        raise OSError(errno.ENOSPC, "No space left on device")


def test_a_key_file_write_that_fails_is_an_error_exit_that_removes_the_empty_file(tmp_path, monkeypatch, capsys):
    f, before = seed(tmp_path)
    kf = tmp_path / "new.key"
    monkeypatch.setattr(kg.os, "fdopen", lambda fd, *a, **k: (os.close(fd), _FullDisk())[1])
    with pytest.raises(SystemExit) as e:
        kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)])
    assert str(e.value).startswith("error: cannot write the key file ") and "fok_" not in str(e.value)
    assert not kf.exists() and f.read_bytes() == before
    monkeypatch.undo()
    assert kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)]) == 0    # a retry works
    assert kf.exists() and "new" in ids(f)


def test_a_key_file_write_interrupted_removes_the_file(tmp_path, monkeypatch):
    kf = tmp_path / "new.key"

    class Interrupted(_FullDisk):
        def write(self, text):
            raise KeyboardInterrupt

    monkeypatch.setattr(kg.os, "fdopen", lambda fd, *a, **k: (os.close(fd), Interrupted())[1])
    with pytest.raises(KeyboardInterrupt):
        kg._write_key_file(str(kf), "fok_x")
    assert not kf.exists()


def test_an_existing_key_file_is_never_overwritten_or_removed(tmp_path):
    kf = tmp_path / "new.key"
    kf.write_text("PRE-EXISTING", encoding="utf-8")
    with pytest.raises(FileExistsError):
        kg._write_key_file(str(kf), "fok_x")
    assert kf.read_text(encoding="utf-8") == "PRE-EXISTING"


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_the_key_file_is_0600_from_creation(tmp_path):
    kf = tmp_path / "new.key"
    kg._write_key_file(str(kf), "fok_x")
    assert (kf.stat().st_mode & 0o777) == 0o600 and kf.read_text(encoding="utf-8") == "fok_x\n"


# --- F-C354-3: a key registered but never shown -------------------------------------------------------------------


def test_the_docstring_states_the_recovery_for_a_key_registered_but_never_shown():
    flat = " ".join(kg.__doc__.split())
    for phrase in ("registered but never shown", "Revoke that row", "NEW operator id", "With --key-file the key file exists whenever the row does"):
        assert phrase in flat, phrase


def test_a_failed_print_after_the_commit_leaves_the_row_registered_as_documented(tmp_path, monkeypatch):
    f, _ = seed(tmp_path)

    class Closed:
        def write(self, text):
            raise BrokenPipeError(errno.EPIPE, "closed")

        def flush(self):
            raise BrokenPipeError(errno.EPIPE, "closed")

    monkeypatch.setattr(sys, "stdout", Closed())
    with pytest.raises(BrokenPipeError):
        kg.main(["--operator-id", "orphan", "--add-to", str(f)])
    assert "orphan" in ids(f)                                        # the declared limit the docstring describes


def test_the_docstring_states_the_lock_and_the_sigkill_limit():
    flat = " ".join(kg.__doc__.split())
    for phrase in ("serialises the whole read-modify-write", "<operators file>.lock", "30 s", "format 2 rotator does not take this lock",
                   "a SIGKILL cannot be handled"):
        assert phrase in flat, phrase


# --- no regression -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("via", ["printed", "key-file"])
def test_a_plain_registration_still_works_under_the_lock(tmp_path, capsys, via):
    f, _ = seed(tmp_path)
    args = ["--operator-id", "new", "--add-to", str(f)] + (["--key-file", str(tmp_path / "k")] if via == "key-file" else [])
    assert kg.main(args) == 0
    out = capsys.readouterr().out
    assert "registered sha256 for 'new'" in out and "new" in ids(f)
    assert ("fok_" in out) == (via == "printed")
