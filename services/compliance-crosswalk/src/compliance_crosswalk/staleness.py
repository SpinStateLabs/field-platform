"""Regulatory-corpus staleness tracking — the crosswalk admits when it is old.

GOVERNANCE RATIONALE (ADR 07 §3/§4): every citation in ``mapping.py`` was
verified on one retrieval date. Regulations move; the mapping table does
not move with them by itself. Rather than silently presenting an aging
crosswalk as current, staleness is a first-class, persisted output: a
framework is flagged the moment a new version or amendment is spotted,
the flag stays visible until a NAMED human reviews it, and the report
states how long each flag has been open — the stale window is itself
evidence, not something to hide. Clearing a flag records who reviewed it;
it never touches the citations. Only a fresh ingestion (a new RETRIEVED
date in mapping.py, with the sources actually re-read) does that.

D4: the same file also holds the regwatch source-hash store (``sources``,
one record per watched URL) and the ``last_check`` summary. Detection
(``regwatch.run_check``) may SET a flag; only :meth:`StaleStore.clear` —
named, CLI-only, never an HTTP route — removes one. Every write is a
:meth:`StaleStore.transaction`: a process-wide thread lock AND an OS-level
exclusive lock on the sidecar ``<flags file>.lock``, both held across
RE-LOAD → modify → persist. So a named ``clear`` — written by another
request, or by the CLI as a separate process (``docker exec … crosswalk
regwatch clear``, the only clear path on an estate) — either lands before
the re-load (and is preserved) or waits until the persist is done (and
applies to what was written). Neither order loses it. Scope: writers on one
host sharing the file (one container, or one volume on one host); advisory
locks on a network filesystem are not claimed. Readers take no lock: the
persist is write-to-a-unique-temp-then-``os.replace``.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, RETRIEVED

log = logging.getLogger("compliance_crosswalk.staleness")

# Derived, never typed twice: the corpus version cannot drift from the
# retrieval date the citations actually carry.
CORPUS_VERSION = f"corpus-{RETRIEVED}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Process-wide, not per instance: the API builds a fresh StaleStore per
# request and the scheduler thread builds its own, so an instance lock would
# serialise nothing. It serialises threads only — other PROCESSES (the CLI)
# are excluded by the OS file lock taken inside transaction() below.
_STORE_LOCK = threading.Lock()

# How long a writer waits for another writer's file lock. A check holds it
# only for compare + persist (fetching happens outside), so seconds at most.
LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.05


class StoreLockTimeout(TimeoutError):
    """Another writer held the stale-flags file lock past the timeout. The
    write did not happen — loud, never a silent skip."""


if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EDEADLK):
                return False
            raise
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        # flock locks belong to the open file description: a second fd in
        # the same process is refused too, as is any other process.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                return False
            raise
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _file_lock(lock_path: Path, timeout: float) -> Iterator[None]:
    """Exclusive OS lock on ``lock_path`` (created if missing, never deleted
    — deleting a lock file races other lockers). Released by the OS if the
    holder dies, so a crashed writer never wedges the store."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        warned = False
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise StoreLockTimeout(
                    f"stale-flags store {lock_path} stayed locked by another "
                    f"writer for {timeout:g} s — nothing was written"
                )
            if not warned:
                log.warning("crosswalk stale-flags store %s is locked by another "
                            "writer; waiting for the store lock (up to %g s)",
                            lock_path, timeout)
                warned = True
            time.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


class StaleStore:
    """Persisted stale flags per framework, with a named-review history.

    On-disk shape (JSON, UTF-8)::

        {"corpus_version": ..., "active": {framework: flag}, "history": [...],
         "sources": {url: hash record}, "last_check": {...} | null}

    ``sources`` and ``last_check`` are written by regwatch (D4); a file
    written before D4 simply lacks them (empty store, never checked).
    """

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = (
                Path(os.environ.get("FIELD_DATA_DIR", "."))
                / "crosswalk_stale_flags.json"
            )
        self.path = Path(path)
        self._active: dict[str, dict] = {}
        self._history: list[dict] = []
        self._sources: dict[str, dict] = {}
        self._last_check: dict | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():  # missing file = empty state, not an error
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._active = dict(data.get("active", {}))
        self._history = list(data.get("history", []))
        self._sources = dict(data.get("sources", {}))
        self._last_check = data.get("last_check")

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "corpus_version": CORPUS_VERSION,
            "active": self._active,
            "history": self._history,
            "sources": self._sources,
            "last_check": self._last_check,
        }
        # Write-then-replace: a reader (another request, the CLI) never sees
        # a half-written file. The temp name is unique per write (pid +
        # thread + random), so two writers never share one temp file.
        tmp = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}."
            f"{secrets.token_hex(4)}.tmp"
        )
        try:
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def transaction(self) -> Iterator["StaleStore"]:
        """Serialised read-modify-write, across threads AND processes. Takes
        the process-wide thread lock, then the OS exclusive lock on
        :attr:`lock_path` (waiting up to ``LOCK_TIMEOUT_SECONDS``, else
        :class:`StoreLockTimeout`), RE-LOADS the file (so a clear persisted
        since this instance loaded survives), yields, and persists only if
        the body did not raise — all before either lock is released."""
        with _STORE_LOCK:
            with _file_lock(self.lock_path, LOCK_TIMEOUT_SECONDS):
                self._load()
                yield self
                self._persist()

    def mark(
        self, framework: str, reason: str, new_version: str | None = None
    ) -> dict:
        """Flag a framework as stale; idempotent on the detection clock.

        Re-marking updates the reason/new_version but keeps the original
        ``flagged_at`` — the stale window measures from FIRST detection,
        and restarting it would understate how long the flag stood.
        """
        with self.transaction():
            return self.apply_mark(framework, reason, new_version)

    def apply_mark(
        self, framework: str, reason: str, new_version: str | None = None
    ) -> dict:
        """The body of :meth:`mark`, for callers already inside
        :meth:`transaction` (regwatch). Persists nothing by itself."""
        if framework not in FRAMEWORKS:
            raise ValueError(
                f"unknown framework {framework!r}; known: {sorted(FRAMEWORKS)}"
            )
        existing = self._active.get(framework)
        flag = {
            "framework": framework,
            "flagged_at": existing["flagged_at"]
            if existing
            else _utc_now().isoformat(),
            "reason": reason,
            "new_version": new_version,
        }
        self._active[framework] = flag
        return flag

    def clear(self, framework: str, reviewed_by: str) -> dict:
        """Clear a flag after review. The review is NAMED — no anonymous
        clears — and the cleared flag is preserved in history, so the
        record of having been stale outlives the flag itself."""
        if not reviewed_by or not reviewed_by.strip():
            raise ValueError(
                "reviewed_by must be a non-empty name — re-review is NAMED"
            )
        with self.transaction():
            if framework not in self._active:
                raise KeyError(framework)
            flag = self._active.pop(framework)
            review = {
                "framework": framework,
                "reviewed_by": reviewed_by,
                "cleared_at": _utc_now().isoformat(),
                "flag": flag,
            }
            self._history.append(review)
        return review

    # --- regwatch source-hash store (D4) ---------------------------------
    # Mutators below persist nothing by themselves: call them inside
    # transaction().

    def source_record(self, url: str) -> dict | None:
        record = self._sources.get(url)
        return dict(record) if record is not None else None

    def sources(self) -> dict[str, dict]:
        return {url: dict(record) for url, record in self._sources.items()}

    def put_source_record(self, url: str, record: dict) -> None:
        self._sources[url] = dict(record)

    def last_check(self) -> dict | None:
        return dict(self._last_check) if self._last_check is not None else None

    def set_last_check(self, record: dict) -> None:
        self._last_check = dict(record)

    def active(self) -> list[dict]:
        return sorted(self._active.values(), key=lambda f: f["framework"])

    def status(self) -> dict:
        """Current staleness posture. Each active flag carries its
        ``stale_window_seconds`` — per ADR 07, the length of the window
        is itself reported, never summarized away."""
        now = _utc_now()
        active = []
        for flag in self.active():
            entry = dict(flag)
            flagged_at = datetime.fromisoformat(flag["flagged_at"])
            entry["stale_window_seconds"] = (now - flagged_at).total_seconds()
            active.append(entry)
        return {
            "corpus_version": CORPUS_VERSION,
            "active": active,
            "history": list(self._history),
            # D4: when the cited sources were last read, by what trigger,
            # and the per-framework outcome; None = never checked.
            "last_check": self.last_check(),
        }


def affected_controls(framework: str) -> list[str]:
    """Control ids whose mapping actually cites the framework.

    Only ``cited`` entries are affected by a regulatory version change —
    pending entries reference no text, so there is nothing to go stale.
    """
    if framework not in FRAMEWORKS:
        raise ValueError(
            f"unknown framework {framework!r}; known: {sorted(FRAMEWORKS)}"
        )
    return sorted(
        control.control_id
        for control in CONTROLS
        if control.citations[framework].status == "cited"
    )
