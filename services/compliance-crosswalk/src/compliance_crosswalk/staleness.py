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
import unicodedata
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

#: S5-18. A reviewer is a NAMED human on one line: the same rule ``evidence_pack._checked_signer`` (the signer) and
#: ``regwatch._named_human`` (--fetched-by) hold; ``_plain_reviewer_name`` below applies it to ``clear``.
MAX_REVIEWER_CHARS = 200
#: free text a flag carries (the reason, the new version) is made one bounded line, not refused: the regwatch scheduler
#: writes the reason itself, and a refusal there would lose the flag
MAX_REASON_CHARS = 2000
MAX_VERSION_CHARS = 100
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def _one_line(value: object, limit: int) -> str:
    """``value`` on one line: control, format and line-break characters become spaces, whitespace runs collapse, and
    the result is cut at ``limit`` characters (ending in an ellipsis)."""
    text = "".join(" " if unicodedata.category(c) in _REFUSED_CATEGORIES else c for c in str(value))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
_LOCK_POLL_SECONDS = 0.05


class StaleStoreError(RuntimeError):
    """The stale-flags file exists but cannot be trusted: unreadable, not UTF-8 JSON, a key given twice, a value of
    the wrong type, a top-level key the store never writes, or no ``active`` key. It is NOT an empty store: an empty store would reopen the evidence-pack gate that a stale flag closes
    (``json.loads`` keeps the LAST of a duplicate key, so a second ``"active"`` used to read as "no flags"). The file is
    never rewritten on this path, so a standing flag stays in it until a NAMED human clears it. The message is fixed:
    the file's name and what is wrong, never the file's text and never the underlying exception's text. A RuntimeError
    on purpose: the pack route's ``except ValueError`` is a 422 for the caller's input, and this is the service's own
    state (503)."""


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


class _DuplicateKey(Exception):
    """Internal: a JSON object named the same key twice."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """``object_pairs_hook`` that refuses a repeated key at any depth (``json.loads`` would keep the last one)."""
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey
        out[key] = value
    return out


def _dump_text(payload: dict) -> str:
    """The store as JSON text that ALWAYS encodes to UTF-8. Readable (``ensure_ascii=False``) unless some string holds a
    lone surrogate (a ``\\ud800`` escape loads as one, and UTF-8 cannot encode it): then the same payload is written
    ASCII-escaped, which is still valid UTF-8 JSON and round-trips every string exactly. Nothing is dropped or replaced,
    so a stored record can never again make every later persist raise (stale detection and ``set-stale`` stay live)."""
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    return text


# Every top-level key _persist writes (the only writer). An existing file with a key outside this set, or without
# `active`, is damaged: a misspelled "active" ("Active", "actives") would otherwise read as an empty store.
_STORE_KEYS = frozenset({"corpus_version", "active", "history", "sources", "last_check"})


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

    def _damaged(self, what: str) -> StaleStoreError:
        return StaleStoreError(
            f"the stale-flags store {self.path.name} is damaged ({what}); "
            "evidence-pack generation stays blocked until it is repaired"
        )

    def _load(self) -> None:
        if not self.path.exists():  # missing file = empty state (never written), not an error
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
        except _DuplicateKey:
            raise self._damaged("a key appears twice") from None
        except OSError as exc:
            raise self._damaged(f"cannot be read: {type(exc).__name__}") from None
        except (ValueError, RecursionError) as exc:  # not UTF-8, not JSON, or too deep: the TYPE only, never the text
            raise self._damaged(f"not valid UTF-8 JSON: {type(exc).__name__}") from None
        if not isinstance(data, dict):
            raise self._damaged("the top level is not an object")
        if "active" not in data:
            raise self._damaged("the 'active' key is missing")
        if not set(data) <= _STORE_KEYS:
            raise self._damaged("a top-level key is not one this store writes")
        active, history = data.get("active", {}), data.get("history", [])
        sources, last_check = data.get("sources", {}), data.get("last_check")
        if not isinstance(active, dict) or not all(isinstance(v, dict) for v in active.values()):
            raise self._damaged("'active' is not an object of objects")
        if not isinstance(history, list):
            raise self._damaged("'history' is not a list")
        if not isinstance(sources, dict):
            raise self._damaged("'sources' is not an object")
        if last_check is not None and not isinstance(last_check, dict):
            raise self._damaged("'last_check' is neither null nor an object")
        self._active = dict(active)
        self._history = list(history)
        self._sources = dict(sources)
        self._last_check = last_check

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
            # flush + fsync the temp file BEFORE the replace: without it a crash or power loss can leave the
            # replaced file empty or partial, the store then fails to load, and a lost write silently reopens the
            # evidence-pack gate that a stale flag closes.
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(_dump_text(payload))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        self._fsync_directory()

    def _fsync_directory(self) -> None:
        """Best effort: make the rename itself durable. Not supported everywhere (Windows cannot open a
        directory), and the data is already safe, so a failure here never fails the write."""
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

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
            "reason": _one_line(reason, MAX_REASON_CHARS),
            "new_version": None if new_version is None else _one_line(new_version, MAX_VERSION_CHARS),
        }
        self._active[framework] = flag
        return flag

    def clear(self, framework: str, reviewed_by: str) -> dict:
        """Clear a flag after review. The review is NAMED — no anonymous
        clears — and the cleared flag is preserved in history, so the
        record of having been stale outlives the flag itself."""
        reviewed_by = _plain_reviewer_name(reviewed_by)    # C-1082 F-CW-10: the same rule as check-file --fetched-by
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
        try:
            return sorted(self._active.values(), key=lambda f: f["framework"])
        except (KeyError, TypeError):   # S10-25 (reduced rebuild of PR 958): a flag with no usable framework
            raise self._damaged("a flag has no usable 'framework'") from None

    def status(self) -> dict:
        """Current staleness posture. Each active flag carries its
        ``stale_window_seconds`` — per ADR 07, the length of the window
        is itself reported, never summarized away."""
        now = _utc_now()
        active = []
        for flag in self.active():
            entry = dict(flag)
            # S10-25 (reduced rebuild of PR 958): a missing, non-text, unparseable or naive flagged_at is a damaged
            # store (503 / exit 2 through the existing handlers), never an unhandled error and never a guessed window
            try:
                flagged_at = datetime.fromisoformat(flag.get("flagged_at"))
            except (TypeError, ValueError):
                raise self._damaged("a flag's flagged_at is missing or not an ISO timestamp") from None
            if flagged_at.tzinfo is None:
                raise self._damaged("a flag's flagged_at has no timezone")
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


#: Unicode categories a reviewer's name may not hold: control, invisible format, line and paragraph separator (the
#: rule of ``regwatch._named_human`` for ``check-file --fetched-by``; a name is a thing you can SEE on one line).
_REFUSED_NAME_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def _plain_reviewer_name(name: object) -> str:
    """The stripped name of the human who cleared a stale flag, or ``ValueError``: blank or not text, holding a
    control, invisible-format or line-break character, or with no letter or digit. The message never echoes the
    name (C-1082 F-CW-10: ``clear`` was the one human gate that only checked "not blank")."""
    import unicodedata

    text = name.strip() if isinstance(name, str) else ""
    if not text:
        raise ValueError("reviewed_by must be a non-empty name — re-review is NAMED")
    if any(unicodedata.category(ch) in _REFUSED_NAME_CATEGORIES for ch in text):
        raise ValueError("reviewed_by must be a plain name (no control characters, invisible format characters or "
                         "line breaks) — re-review is NAMED")
    if len(text) > MAX_REVIEWER_CHARS:
        raise ValueError(f"reviewed_by is {len(text)} characters; the limit is {MAX_REVIEWER_CHARS}")
    if not any(ch.isalnum() for ch in text):
        raise ValueError("reviewed_by must name a human: it needs at least one letter or digit — re-review is NAMED")
    return text
