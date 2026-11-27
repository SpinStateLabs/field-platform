"""Shared, dependency-free helpers for the test estates that boot estate_harness.py.

``harness_wait(default)`` reads FIELD_TEST_HARNESS_WAIT (seconds). Empty,
non-numeric, nan, inf, zero and negative values fall back to ``default``, and it
never raises, so it is safe to call before ``subprocess.Popen`` (a bad value can
never leak a harness). With the variable unset it returns ``default``, i.e.
behaviour is unchanged.

``kills_proc_on_init_failure`` makes a class's ``__init__`` terminate any
``proc`` / ``sentinel`` subprocess it already started if the constructor raises
anywhere between ``Popen`` and ``return`` (the constructor's caller never gets
an object to ``close()``).
"""

from __future__ import annotations

import contextlib
import functools
import math
import os
import socket
import time
import uuid
from pathlib import Path

ENV = "FIELD_TEST_HARNESS_WAIT"


def harness_wait(default: float) -> float:
    raw = os.environ.get(ENV, "")
    try:
        value = float(raw.strip())
    except ValueError:
        return float(default)
    if not math.isfinite(value) or value <= 0:
        return float(default)
    return value


def new_port_file(directory) -> Path:
    """A path nothing has written yet, for one start of estate_harness.py with ``0 DATA --port-file PATH``."""
    return Path(directory) / f"harness-{uuid.uuid4().hex}.port"


def port_the_process_took(port_file: Path, proc, deadline: float, what: str = "harness") -> int:
    """The number a test server wrote after binding port 0 itself (``deadline`` is a ``time.time()`` value)."""
    while time.time() < deadline:
        if port_file.exists():
            return int(port_file.read_text(encoding="ascii"))
        if proc.poll() is not None:
            raise RuntimeError(f"{what} exited early: {proc.returncode}")
        time.sleep(0.1)
    raise RuntimeError(f"{what} did not come up")


@contextlib.contextmanager
def nothing_listens():
    """A URL with no server behind it. The port stays bound, without listen(), for as long as it is used, so a
    connection fails and no other server can take the number."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        yield f"http://127.0.0.1:{s.getsockname()[1]}"


def terminate(proc) -> None:
    """Stop a subprocess.Popen (or None), tolerating one that already exited."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=20)
    except Exception:  # noqa: BLE001 - last resort below
        try:
            proc.kill()
            proc.wait(timeout=20)
        except Exception:  # noqa: BLE001
            pass


def kills_proc_on_init_failure(cls):
    original = cls.__init__

    @functools.wraps(original)
    def __init__(self, *args, **kwargs):
        try:
            original(self, *args, **kwargs)
        except BaseException:
            for name in ("proc", "sentinel"):
                terminate(getattr(self, name, None))
            raise

    cls.__init__ = __init__
    return cls
