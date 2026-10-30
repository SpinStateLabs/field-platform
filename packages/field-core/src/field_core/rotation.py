"""Operator key rotator core (key rotation design v0.2 section 4, slice R4a).

Plain code, no model. One run (``Rotator.run_once``) rotates at most ONE
machine identity of one estate through the design 4.3 sequence::

    0 PREFLIGHT  1 LOCK  2 PRECHECK  3 GENERATE  4 PUBLISH  5 VERIFY-NEXT
    6 SWITCH  7 CONFIRM-SWITCH  8 SOAK  9 PROMOTE  9b VERIFY-CURRENT
    10 CONFIRM-REFUSED  11 CLEANUP

and is resumed by the next run from its journal after a crash or an
unfinished soak. Everything it touches over the network goes through an
``Estate`` (the eight services' ``/operator/rotation-state`` and
``/operator/verify-hash``, the open ``/health`` for ``build_sha``, and
ledger appends); tests drive it with fakes, ``tools/operator_rotate.py``
supplies the HTTP one. Files (the operators file, key files, the state
directory) are touched directly, on one filesystem, with atomic renames.

What this module guarantees (each pinned by tests and a mutant):

* **Keys.** A new key is generated HERE (``secrets``), written once to
  ``<key file>.next`` with ``O_CREAT|O_EXCL`` and mode 0600, and never
  printed, logged, ledgered, journaled or sent anywhere. Only its sha256
  enters the operators file; only 16-hex fingerprints enter events, the
  journal, the status file and the run summary. The whole run runs under
  umask 077, and every file it creates (``.next``, the key ``.prev`` link,
  ``operators.json.prev``, the journal, the status file, the lock) is 0600.
* **Write policy.** Every operators-file write passes :func:`diff_guard`
  first: the candidate may differ from the live file only in the header
  (``format``, ``generation``, ``issued_at``, ``issued_by``) and in the
  TARGET row's key fields (``key_sha256``, ``key_created_at``,
  ``key_not_after``, ``next_key``); rows, their order, ids, ``status``,
  ``scopes``, ``names``, ``event_prefixes``, ``rotation``, ``auth`` and
  everything else stay byte-equal (canonical JSON), the generation only goes
  up and the break-glass (sealed) row is never a target. The one format 1 ->
  format 2 migration has its own mode (below). A refused candidate is never
  written (``keyrotation.failed {reason_class: policy}``). Every candidate is
  also parsed with the installed R1 parser (``operator_auth``) before it is
  written (``reason_class: validation``).
* **Generations.** Every write goes ABOVE the highest generation ever issued:
  ``max(live, every service's reported generation, the status file's
  high-water mark) + 1``, the high-water mark recorded before the write.
  The verifiers' retired-hash memory (R1, design 2.4) refuses a hash that
  comes back in a file at or below the generation that removed it, so a
  write at "live + 1" after a restore would refuse brand-new keys (R1 review
  F6) and a ``.prev`` renamed back after PROMOTE would refuse the old key
  (R1 review F2).
* **Auto-revert** re-publishes the ``rotation/operators.json.prev`` CONTENT
  at a new generation (above the high-water mark) through ``diff_guard``; it
  never renames ``.prev`` back.
* **Never lock out** (design 6.3 invariant 1): the old key file is kept as
  ``<key>.prev`` until VERIFY-CURRENT (9b: every service answers ``current``
  for sha256 of the LIVE key file) and CONFIRM-REFUSED (10: every service
  answers ``none`` for the old hash) both pass; only then CLEANUP removes it.
  A failure before PROMOTE aborts; a failure at or after PROMOTE reverts the
  file (PROMOTE not seen, 9b) or keeps everything for the next run (10), and
  is never key-restoring: the journal goes back to ``promote`` (outside
  ``BEFORE_PROMOTE``, so the 24 h abort limit never applies) and the next run
  promotes again (kr-r4a review F1, F2).
* **Abort acts on live state** (design 4.4; kr-r4a review fix (b)): it
  restores ``<key>.prev`` onto the key file only when the LIVE row's current
  hash is sha256(``<key>.prev``); it removes ``next_key`` by editing the LIVE
  document (the target's ``next_key`` dropped, its other key fields kept, the
  expiry an incident rotation shortened restored from the pre-publish copy
  when that copy's row holds the same current hash), never by re-publishing a
  ``.prev`` that may hold both keys; and it refuses
  (``keyrotation.failed {reason_class: internal}``, journal moved forward to
  ``promote``) when the live current slot already holds the new key.

Format 1 -> format 2 migration (design 2.2 step 2): when the live file is
format 1, the run's only write is the migration. Every row gains
``rotation``, ``key_not_after`` (machine rows this rotator manages:
``now + 75 d + jitter(id)``, staggered; the break-glass row: ``sealed`` and no
expiry; every other row: the configured ``unmanaged_rotation`` and
``unmanaged_not_after``) and, from its ``created_at``, ``key_created_at``.
Keygen and the Stage 0 assembler write ``created_at`` as
``YYYY-MM-DDTHH:MM:SS+00:00``, which the format 2 parser refuses; the
migration normalises exactly that form to ``...Z`` (the same instant) and
changes nothing else. The candidate is validated with the same R1 parser, so
an unknown legacy scope, an unknown legacy field or a bad ``created_at``
blocks the MIGRATION (nothing written), never the estate. The frozen event
schema has no "migrated" event: the migration is ledgered as
``keyrotation.reconciled`` naming the rows that gained key fields.

A migration that is written but not seen is still ledgered as
``keyrotation.reconciled`` (its generation and file sha) before the
``keyrotation.failed``; on ``registry_error`` the exact pre-migration bytes
(kept in ``rotation/operators.json.prev``) are written back, which is safe
for the retired-hash memory because the migration removes no hash (kr-r4a
review ruling 7). Plain ``publish_not_seen`` keeps the format 2 file.

Not in this slice (design section 8): ``--abort-inflight`` / ``--reconcile``
/ ``--extend`` / ``--downgrade-format`` / ``--accept-roster`` as operator
commands and recovery mode (R9), the compose e2e (R4b), typed spool requests
in ``diff_guard`` (H2, B1), and the JOB'S OWN LOCK for job identities (design
4.2 O11, 4.3 step 1 "plus the job's lock"): this slice takes only the estate
lock, so a job identity must not go into a live rotator config before R5
takes the job's lock (kr-r4a review F7).
A foreign edit of the operators file is detected and skipped
(``keyrotation.skipped {skip_reason: foreign_edit}``) with its class (key
slots only, or not) recorded in the status file for R9's reconcile.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from field_core import operator_auth as oa
from field_core import rotation_events as ev

log = logging.getLogger("field.rotation")

DAY = 86400
#: design 4.2 (K2): rotate every 30 days, each id's due day offset by
#: sha256(id) mod 7 days; a key expires 75 days after it is created
ROTATE_EVERY_S = 30 * DAY
JITTER_SPAN_S = 7 * DAY
KEY_LIFETIME_S = 75 * DAY
#: design 4.2: at least 6 h between two rotations on an estate (normal mode)
ESTATE_SPACING_S = 6 * 3600
#: design 4.3 step 8: at least 15 minutes and three observer ticks
MIN_SOAK_S = 15 * 60
SOAK_TICKS = 3
#: design 4.3 step 4: the NEXT slot is valid from 5 minutes before PUBLISH
NOT_BEFORE_SKEW_S = 5 * 60
#: design 4.3 step 7: the daemon shows the new fingerprint within 30 s
CONFIRM_SWITCH_S = 30
#: design 4.4 (O4): an unfinished rotation that has not reached PROMOTE in 24 h
INFLIGHT_LIMIT_S = 24 * 3600
#: design 2.4 item 2: an incident rotation shortens the compromised key's
#: expiry to PUBLISH + soak + 1 h
INCIDENT_EXTRA_S = 3600
#: K6 default for rows this rotator does not manage (humans until H4)
UNMANAGED_LIFETIME_S = 120 * DAY

SERVICES = tuple(sorted(ev.SERVICES))
KEY_ROW_FIELDS = frozenset({"key_sha256", "key_created_at", "key_not_after", "next_key"})
HEADER_FIELDS = frozenset({"format", "generation", "issued_at", "issued_by"})
#: fields the migration may ADD to a format 1 row
MIGRATION_ADDED_ROW_FIELDS = frozenset({"rotation", "key_created_at", "key_not_after"})
KINDS = frozenset({"daemon", "job", "self"})
#: journal phases from which an abort (design 4.4) is allowed
BEFORE_PROMOTE = ("generate", "publish", "verify_next", "switch", "confirm_switch", "soak")
#: the journal phase after a post-PROMOTE failure (PROMOTE not seen, 9b): the
#: next run resumes at PROMOTE; it is outside BEFORE_PROMOTE, so no 24 h abort
#: (no key restore) ever runs against a promoted or both-keys registry
#: (kr-r4a review F1, F2)
POST_PROMOTE_RETRY = "promote"
#: failures at or after PROMOTE after which the rotator stops retrying that
#: identity and halts with a CRITICAL log line (kr-r4a review condition 2):
#: both keys stay valid, every file is kept, a human or R9 acts. The hourly
#: ``keyrotation.failed`` continues.
POST_PROMOTE_MAX_FAILURES = 10

# run results / exit codes (tools/operator_rotate.py)
EXIT_OK = 0          # rotated, migrated, resumed, in progress, or nothing due
EXIT_FAILED = 1      # a phase failed (reverted or kept for the next run)
EXIT_USAGE = 2
EXIT_LOCKED = 3      # design 4.3 step 1: the estate lock is held; nothing written
EXIT_SKIPPED = 4     # freeze, precheck, foreign edit or clock: nothing written

# file names inside the state directory (design 4.3, O18)
LOCK_NAME = "rotation.lock"
FREEZE_NAME = "rotation.freeze"
STATUS_NAME = "status.json"
PREV_NAME = "operators.json.prev"
JOURNAL_PREFIX = "journal-"

_PLUS_ZERO_SUFFIX = "+00:00"

PhaseHook = Callable[[str], None]


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------

class PolicyRefused(Exception):
    """diff_guard refused a candidate. The message names fields and row
    numbers / ids only, never a value."""


class LockHeld(Exception):
    pass


class EstateError(Exception):
    """A service or the ledger did not answer (transport error, non-2xx)."""


class _Stop(Exception):
    """Internal: end this run with ``code`` after the failure was handled."""

    def __init__(self, code: int, summary: dict[str, Any]):
        super().__init__(summary.get("result", "stopped"))
        self.code = code
        self.summary = summary


# --------------------------------------------------------------------------
# the estate interface (HTTP in tools/operator_rotate.py, fakes in tests)
# --------------------------------------------------------------------------

class Estate(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

    def clock_synced(self) -> bool | None: ...

    def build_sha(self, service: str) -> str | None:
        """The service's open ``/health`` ``build_sha``."""

    def rotation_state(self, service: str) -> dict[str, Any]:
        """The service's ``GET /operator/rotation-state`` (R2)."""

    def verify_hash(self, service: str, operator_id: str, key_sha256: str) -> dict[str, Any]:
        """The service's ``POST /operator/verify-hash`` answer (R2): a hash,
        never a key."""

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """A ledger append under the rotator's own identity; returns the
        stored event when the ledger returns one."""

    def refusals(self, operator_id: str, since: float) -> int:
        """``operator.unauthenticated`` / ``operator.refused`` rows naming
        ``operator_id`` ledgered at or after ``since``."""


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Identity:
    """A machine identity this rotator rotates. ``daemon``: a service reads the
    key file per call and shows its fingerprint on rotation-state
    (``service``); ``job``: a CLI reads it at its next run; ``self``: the
    rotator's own ledger identity."""
    operator_id: str
    key_path: str
    kind: str = "daemon"
    service: str | None = None
    soak_s: int = MIN_SOAK_S

    def __post_init__(self) -> None:
        if not oa.printable_id(self.operator_id):
            raise ValueError("identity operator_id is not an operator id")
        if self.kind not in KINDS:
            raise ValueError(f"identity kind must be one of {sorted(KINDS)}")
        if self.kind == "daemon" and self.service not in ev.SERVICES:
            raise ValueError("a daemon identity names one of the eight services")
        if oa.is_breakglass(self.operator_id):
            raise ValueError("the break-glass identity is never rotated by the rotator")


@dataclass(frozen=True)
class Settings:
    estate: str
    operators_file: str
    state_dir: str
    issued_by: str
    identities: tuple[Identity, ...]
    services: tuple[str, ...] = SERVICES
    #: the rotator's own build sha (FIELD_BUILD_SHA); None = unknown (PREFLIGHT skips)
    build_sha: str | None = None
    observer_tick_s: int = 60
    #: how long PUBLISH / PROMOTE wait for every service to show the new file
    publish_wait_s: int | None = None
    poll_s: float = 2.0
    confirm_switch_s: int = CONFIRM_SWITCH_S
    #: the longest a run sleeps inside SOAK; a longer remaining soak ends the
    #: run ("in progress") and the next run resumes it
    max_wait_s: int = MIN_SOAK_S + 300
    unmanaged_rotation: str = "remote"
    #: epoch seconds; None = migration time + UNMANAGED_LIFETIME_S
    unmanaged_not_after: int | None = None

    def __post_init__(self) -> None:
        if not ev.FIELD_TYPES["estate"](self.estate):
            raise ValueError("estate must be a short lower-case name")
        if not oa.printable_id(self.issued_by):
            raise ValueError("issued_by is not an operator id")
        if self.unmanaged_rotation not in ("auto", "remote"):
            raise ValueError("unmanaged_rotation must be 'auto' or 'remote'")
        ids = [i.operator_id for i in self.identities]
        if len(set(ids)) != len(ids):
            raise ValueError("an identity is listed twice")
        if not set(self.services) <= ev.SERVICES or not self.services:
            raise ValueError("services must be operator-block service names")

    @property
    def publish_wait(self) -> float:
        return float(self.publish_wait_s if self.publish_wait_s is not None
                     else self.observer_tick_s + 30)

    def identity(self, operator_id: str) -> Identity | None:
        for i in self.identities:
            if i.operator_id == operator_id:
                return i
        return None


# --------------------------------------------------------------------------
# small pure helpers
# --------------------------------------------------------------------------

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def encode_doc(doc: Any) -> bytes:
    """The bytes the rotator writes for an operators document."""
    return (json.dumps(doc, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fp16(key_sha256_hex: str) -> str:
    return ev.fingerprint(key_sha256_hex)


def jitter_s(operator_id: str) -> int:
    """design 4.2: each id's due day is offset by sha256(id) mod 7 days."""
    return int(hashlib.sha256(operator_id.encode("utf-8")).hexdigest(), 16) % JITTER_SPAN_S


def generate_key() -> str:
    """A new operator key, the ``operator_keygen`` form (F16). Never printed."""
    return oa.KEY_PREFIX + secrets.token_urlsafe(32)


def normalise_created_at(value: Any) -> Any:
    """design 2.2 / R1 review 5d: keygen and the Stage 0 assembler write
    ``created_at`` as ``YYYY-MM-DDTHH:MM:SS+00:00``. That exact form becomes
    ``...Z`` (the same instant); anything else is returned unchanged (the
    format 2 parser then decides, and refuses what it does not accept)."""
    if isinstance(value, str) and value.endswith(_PLUS_ZERO_SUFFIX):
        candidate = value[: -len(_PLUS_ZERO_SUFFIX)] + "Z"
        if oa.parse_time(candidate) is not None:
            return candidate
    return value


def _rows_of(doc: Any) -> list | None:
    rows = doc.get("operators") if isinstance(doc, dict) else doc
    return rows if isinstance(rows, list) else None


def _doc_format(doc: Any) -> int:
    return doc["format"] if isinstance(doc, dict) and type(doc.get("format")) is int else 1


def _generation(doc: Any) -> int:
    g = doc.get("generation") if isinstance(doc, dict) else None
    return g if type(g) is int else 0


def _row_index(doc: Any, operator_id: str) -> int | None:
    for i, r in enumerate(_rows_of(doc) or []):
        if isinstance(r, dict) and r.get("operator_id") == operator_id:
            return i
    return None


# --------------------------------------------------------------------------
# diff_guard (design 4.3, S2, O8)
# --------------------------------------------------------------------------

def diff_guard(current: Any, candidate: Any, targets: Iterable[str], *,
               migration: bool = False) -> None:
    """Refuse (PolicyRefused) any candidate that is not an allowed rotator
    write of ``current``. Allowed differences:

    * header: ``format`` (stays 2; 1 -> 2 only with ``migration``),
      ``generation`` (must go UP), ``issued_at``, ``issued_by``;
    * in a TARGET row (by id) only ``key_sha256``, ``key_created_at``,
      ``key_not_after`` and ``next_key`` (a sealed / break-glass row is never a
      target);
    * with ``migration`` (format 1 -> 2, no targets): every row may GAIN
      ``rotation``, ``key_created_at`` and ``key_not_after``, and
      ``created_at`` may change only from the ``+00:00`` form to the ``Z`` form
      of the same instant.

    Everything else is byte-equal in canonical JSON: the top-level fields, the
    number and ORDER of rows, and every other field of every row (``operator_id``,
    ``status``, ``scopes``, ``names``, ``event_prefixes``, ``rotation``,
    ``auth``, ``passkeys``, ``created_at``, unknown fields, presence included).
    Messages name fields and row numbers only."""
    targets = frozenset(targets)
    if migration and targets:
        raise PolicyRefused("a migration has no target rows")
    if not isinstance(candidate, dict) or candidate.get("format") != oa.FORMAT_2 \
            or type(candidate.get("format")) is not int:
        raise PolicyRefused("the rotator writes format 2 files only")
    cur_format = _doc_format(current)
    if migration:
        if cur_format != 1:
            raise PolicyRefused("a migration starts from a format 1 file")
    elif cur_format != oa.FORMAT_2 or not isinstance(current, dict):
        raise PolicyRefused("the live file is not format 2 (migrate first)")
    if type(candidate.get("generation")) is not int or \
            candidate["generation"] <= _generation(current):
        raise PolicyRefused("generation must go up")
    cur_top = current if isinstance(current, dict) else {"operators": current}
    for name in sorted((set(cur_top) | set(candidate)) - HEADER_FIELDS - {"operators"},
                       key=str):
        if (name in cur_top) != (name in candidate) or \
                canonical(cur_top.get(name)) != canonical(candidate.get(name)):
            raise PolicyRefused(f"top-level field {_shown(name)} changed")
    cur_rows, cand_rows = _rows_of(current), _rows_of(candidate)
    if cur_rows is None or cand_rows is None:
        raise PolicyRefused("operators is not a list")
    if len(cur_rows) != len(cand_rows):
        raise PolicyRefused("rows added or removed")
    sealed = {r.get("operator_id") for r in cur_rows
              if isinstance(r, dict) and (r.get("rotation") == "sealed"
                                          or oa.is_breakglass(r.get("operator_id")))}
    if targets & sealed:
        raise PolicyRefused("the break-glass row is never a rotator target")
    seen_targets = set()
    for i, (a, b) in enumerate(zip(cur_rows, cand_rows), 1):
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise PolicyRefused(f"row {i} is not an object")
        if canonical(a.get("operator_id")) != canonical(b.get("operator_id")) or \
                ("operator_id" in a) != ("operator_id" in b):
            raise PolicyRefused(f"row {i}: operator_id changed (rows re-ordered or renamed)")
        oid = a.get("operator_id")
        is_target = isinstance(oid, str) and oid in targets
        if is_target:
            seen_targets.add(oid)
        for name in sorted(set(a) | set(b), key=str):
            same = (name in a) == (name in b) and canonical(a.get(name)) == canonical(b.get(name))
            if same:
                continue
            if is_target and name in KEY_ROW_FIELDS:
                continue
            if migration and name in MIGRATION_ADDED_ROW_FIELDS and name not in a:
                continue
            if migration and name == "created_at" and name in a and name in b \
                    and normalise_created_at(a[name]) == b[name] and b[name] != a[name]:
                continue
            raise PolicyRefused(f"row {i}: field {_shown(name)} changed")
    if seen_targets != targets:
        raise PolicyRefused("a target row is missing")


def _shown(name: Any) -> str:
    return oa._shown_fields([name])


# --------------------------------------------------------------------------
# file helpers (one filesystem, atomic renames, 0600)
# --------------------------------------------------------------------------

def _write_private(path: Path, data: bytes) -> None:
    """Replace ``path`` atomically with ``data``: a 0600 temp file created
    exclusively in the same directory, fsynced, then renamed over it."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(str(tmp))
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    if hasattr(os, "O_DIRECTORY"):
        with contextlib.suppress(OSError):
            dfd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)


def _write_operators(path: Path, data: bytes) -> None:
    """The operators file keeps its permission bits (services read it through
    a read-only mount); the temp file is a dot-file in the same directory."""
    path = Path(path)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(OSError):
            os.chmod(str(tmp), mode)
        os.replace(str(tmp), str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(str(tmp))
        raise
    _fsync_dir(path.parent)


def write_new_key(path: Path, key: str) -> None:
    """design 4.3 step 3 / F16: exclusive create, 0600, never via a temp file
    with umask-default permissions."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(key + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def key_file_sha(path: Path) -> str | None:
    """sha256 of the key a daemon would present from ``path`` (the same read
    as ``operator_auth``), or None when the file is absent or unusable."""
    if not Path(path).exists():
        return None
    key = oa._key_from_file(str(path))
    return oa.key_sha256(key) if key else None


class _EstateLock:
    """Non-blocking exclusive lock on ``rotation.lock`` (0600)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.fd: int | None = None

    def acquire(self) -> None:
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.name == "nt":  # pragma: no cover - exercised on Windows dev hosts
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise LockHeld() from None
        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            if os.name == "nt":  # pragma: no cover
                import msvcrt

                with contextlib.suppress(OSError):
                    os.lseek(self.fd, 0, 0)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None


@contextlib.contextmanager
def _umask_077():
    old = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(old)


# --------------------------------------------------------------------------
# journal and status
# --------------------------------------------------------------------------

@dataclass
class Journal:
    """One in-flight rotation (design 4.3: written BEFORE each side effect).
    Fingerprints only; never a key or a full hash."""
    run_id: str
    operator_id: str
    reason: str
    started_at: int
    phase: str = "generate"
    old_fp: str = ""
    new_fp: str | None = None
    soak_started_at: int | None = None
    published_generation: int | None = None
    promoted_generation: int | None = None
    emitted: list[str] = field(default_factory=list)
    post_promote_failures: int = 0

    def to_bytes(self) -> bytes:
        return (json.dumps(self.__dict__, sort_keys=True, indent=1) + "\n").encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Journal":
        raw = json.loads(data.decode("utf-8"))
        return cls(**{k: raw[k] for k in cls.__dataclass_fields__ if k in raw})


# --------------------------------------------------------------------------
# migration (design 2.2 step 2)
# --------------------------------------------------------------------------

def migration_candidate(current: Any, settings: Settings, *, now: int,
                        generation: int) -> tuple[dict, list[str]]:
    """The format 2 document the migration writes for a format 1 ``current``,
    and the ids of the rows that gained key fields. Nothing is dropped: a
    format 1 field or top-level key the format 2 parser refuses stays in the
    candidate, so the parser blocks the migration."""
    rows = _rows_of(current)
    if rows is None:
        raise PolicyRefused("operators is not a list")
    managed = {i.operator_id for i in settings.identities}
    unmanaged_until = (settings.unmanaged_not_after if settings.unmanaged_not_after is not None
                       else now + UNMANAGED_LIFETIME_S)
    out_rows = []
    ids = []
    for r in rows:
        if not isinstance(r, dict):
            out_rows.append(r)
            continue
        row = dict(r)
        oid = row.get("operator_id")
        if "created_at" in row:
            row["created_at"] = normalise_created_at(row["created_at"])
            if oa.parse_time(row["created_at"]) is not None:
                row["key_created_at"] = row["created_at"]
        if isinstance(oid, str) and oa.is_breakglass(oid):
            row["rotation"] = "sealed"
        elif isinstance(oid, str) and oid in managed:
            row["rotation"] = "auto"
            row["key_not_after"] = oa.format_time(now + KEY_LIFETIME_S + jitter_s(oid))
        else:
            row["rotation"] = settings.unmanaged_rotation
            row["key_not_after"] = oa.format_time(unmanaged_until)
        out_rows.append(row)
        if oa.printable_id(oid) and len(ids) < ev.MAX_OPERATOR_IDS:
            ids.append(oid)
    head = {k: v for k, v in current.items() if k not in ("operators", "format")} \
        if isinstance(current, dict) else {}
    doc = {"format": oa.FORMAT_2, "generation": generation,
           "issued_at": oa.format_time(now), "issued_by": settings.issued_by,
           **head, "operators": out_rows}
    return doc, ids


# --------------------------------------------------------------------------
# the rotator
# --------------------------------------------------------------------------

class Rotator:
    def __init__(self, settings: Settings, estate: Estate, *,
                 hook: PhaseHook | None = None):
        self.s = settings
        self.e = estate
        self._hook = hook or (lambda point: None)
        self.state = Path(settings.state_dir)
        self.ops = Path(settings.operators_file)

    # -- paths ---------------------------------------------------------------

    def _journal_path(self, operator_id: str) -> Path:
        return self.state / f"{JOURNAL_PREFIX}{operator_id}.json"

    @staticmethod
    def _next(identity: Identity) -> Path:
        return Path(identity.key_path + ".next")

    @staticmethod
    def _key_prev(identity: Identity) -> Path:
        return Path(identity.key_path + ".prev")

    # -- status ------------------------------------------------------------

    def _status(self) -> dict[str, Any]:
        p = self.state / STATUS_NAME
        try:
            raw = json.loads(p.read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save_status(self, **changes: Any) -> dict[str, Any]:
        st = self._status()
        st.update(changes)
        st["v"] = 1
        st["estate"] = self.s.estate
        st["updated_at"] = oa.format_time(int(self.e.now()))
        _write_private(self.state / STATUS_NAME,
                       (json.dumps(st, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        return st

    # -- journal -------------------------------------------------------------

    def _load_journals(self) -> tuple[list[Journal], list[str]]:
        """(readable journals, operator ids / names of unreadable ones)."""
        out, bad = [], []
        for p in sorted(self.state.glob(f"{JOURNAL_PREFIX}*.json")):
            try:
                out.append(Journal.from_bytes(p.read_bytes()))
            except (OSError, ValueError, TypeError, KeyError):
                log.error("rotation journal unreadable: %s", p.name)
                bad.append(p.name[len(JOURNAL_PREFIX):-len(".json")])
        return out, bad

    def _save_journal(self, j: Journal) -> None:
        _write_private(self._journal_path(j.operator_id), j.to_bytes())

    def _set_phase(self, j: Journal, phase: str) -> None:
        j.phase = phase
        self._save_journal(j)
        self._save_status(in_flight={"operator_id": j.operator_id, "phase": phase,
                                     "run_id": j.run_id})

    def _end_journal(self, j: Journal) -> None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(str(self._journal_path(j.operator_id)))
        self._save_status(in_flight=None)

    # -- events --------------------------------------------------------------

    def _emit(self, event_type: str, payload: dict[str, Any], j: Journal | None = None,
              once: bool = True) -> dict[str, Any] | None:
        """Validate against the frozen schema, then append. With a journal,
        a once-per-run event already appended is not appended again on resume."""
        if j is not None and once and event_type in j.emitted:
            return None
        ev.validate(event_type, payload)
        result = self.e.append(event_type, payload)
        if j is not None and once:
            j.emitted.append(event_type)
            self._save_journal(j)
        return result

    def _run_fields(self, j: Journal) -> dict[str, Any]:
        return {"operator_id": j.operator_id, "estate": self.s.estate, "run_id": j.run_id}

    def _skip(self, reason: str, operator_id: str | None, code: int = EXIT_SKIPPED,
              detail: str | None = None) -> _Stop:
        run_id = self._new_run_id()
        with contextlib.suppress(Exception):
            self._emit("keyrotation.skipped", {"operator_id": operator_id,
                                               "estate": self.s.estate, "run_id": run_id,
                                               "skip_reason": reason})
        summary = {"result": "skipped", "skip_reason": reason, "operator_id": operator_id}
        if detail:
            summary["detail"] = detail
        return _Stop(code, summary)

    def _new_run_id(self) -> str:
        return f"{self.s.estate}-{int(self.e.now())}-{secrets.token_hex(4)}"

    # -- reading the estate ---------------------------------------------------

    def _read_live(self) -> tuple[bytes, Any]:
        data = self.ops.read_bytes()
        return data, json.loads(data.decode("utf-8-sig"))

    def _states(self) -> dict[str, dict[str, Any] | None]:
        out: dict[str, dict[str, Any] | None] = {}
        for svc in self.s.services:
            try:
                out[svc] = self.e.rotation_state(svc)
            except EstateError:
                out[svc] = None
        return out

    def _next_generation(self, live_doc: Any, states: dict | None = None) -> int:
        """Above the highest generation ever issued: live, every service's
        reported generation, and the status file's high-water mark."""
        states = self._states() if states is None else states
        seen = [_generation(live_doc), int(self._status().get("high_generation") or 0)]
        seen += [s.get("registry_generation") or 0 for s in states.values()
                 if isinstance(s, dict) and type(s.get("registry_generation")) is int]
        return max(seen) + 1

    def _seen(self, sha16: str) -> str | None:
        """None when every service shows the file ``sha16`` with no registry
        error; else the reason class (``registry_error`` when any service
        reports one, else ``publish_not_seen``)."""
        states = self._states()
        if any(isinstance(st, dict) and st.get("last_registry_error") is not None
               for st in states.values()):
            return "registry_error"
        if all(isinstance(st, dict) and st.get("registry_sha256_prefix") == sha16
               for st in states.values()):
            return None
        return "publish_not_seen"

    def _wait_seen(self, sha16: str) -> str | None:
        """design 4.3 step 4: one observer tick for all services to show the
        new file with no registry error. None = seen, else the reason class."""
        deadline = self.e.now() + self.s.publish_wait
        while True:
            reason = self._seen(sha16)
            if reason is None or self.e.now() >= deadline:
                return reason
            self.e.sleep(self.s.poll_s)

    def _daemon_fp(self, identity: Identity) -> str | None:
        try:
            st = self.e.rotation_state(identity.service)
        except EstateError:
            return None
        return st.get("identity_key_fp") if isinstance(st, dict) else None

    def _wait_daemon_fp(self, identity: Identity, want: str) -> bool:
        deadline = self.e.now() + self.s.confirm_switch_s
        while True:
            if self._daemon_fp(identity) == want:
                return True
            if self.e.now() >= deadline:
                return False
            self.e.sleep(self.s.poll_s)

    def _verify_all(self, operator_id: str, sha: str, want: str) -> bool:
        """Every service answers ``want`` (current / next / none) for ``sha``
        from its own parse; ``current`` and ``next`` must also be matchable
        now and not retired."""
        for svc in self.s.services:
            try:
                a = self.e.verify_hash(svc, operator_id, sha)
            except EstateError:
                return False
            if not isinstance(a, dict) or a.get("matched") != want:
                return False
            if want != "none" and (a.get("matchable_now") is not True
                                   or a.get("retired") is not False):
                return False
        return True

    # -- writing the operators file ------------------------------------------

    def _publish(self, live_doc: Any, candidate: dict, targets: Iterable[str], *,
                 save_prev: bool, live_bytes: bytes, migration: bool = False) -> tuple[int, str]:
        """diff_guard, validate with the installed parser, record the
        high-water mark, (optionally) keep the live file as
        ``rotation/operators.json.prev``, then rename the candidate in.
        Returns (generation, sha16 of the bytes written)."""
        diff_guard(live_doc, candidate, targets, migration=migration)
        oa.parse_registry_doc(candidate, require_active=True)
        data = encode_doc(candidate)
        gen = candidate["generation"]
        if save_prev:
            _write_private(self.state / PREV_NAME, live_bytes)
        st = self._status()
        self._save_status(high_generation=max(gen, int(st.get("high_generation") or 0)),
                          pending_sha256=sha256_hex(data))
        self._hook("before_operators_write")
        _write_operators(self.ops, data)
        self._hook("after_operators_write")
        self._save_status(last_written_sha256=sha256_hex(data), pending_sha256=None)
        return gen, sha256_hex(data)[:16]

    def _header(self, doc: dict, generation: int) -> dict:
        out = dict(doc)
        out["generation"] = generation
        out["issued_at"] = oa.format_time(int(self.e.now()))
        out["issued_by"] = self.s.issued_by
        return out

    def _revert(self, j: Journal, phase: str, reason: str, *, event: str) -> _Stop:
        """Re-publish the ``rotation/operators.json.prev`` CONTENT at a new
        generation above the high-water mark (never a rename back), through
        diff_guard, then ledger ``event`` (failed / aborted) with reverted."""
        reverted, gen, sha16 = False, None, None
        try:
            prev_doc = json.loads((self.state / PREV_NAME).read_bytes().decode("utf-8-sig"))
            live_bytes, live_doc = self._read_live()
            candidate = self._header(prev_doc, self._next_generation(live_doc))
            gen, sha16 = self._publish(live_doc, candidate, [j.operator_id], save_prev=False,
                                       live_bytes=live_bytes)
            reverted = True
            if self._wait_seen(sha16) is not None:
                log.error("rotation: the reverted file was not seen by every service")
        except (OSError, ValueError, PolicyRefused, oa.RegistryUnavailable) as exc:
            log.error("rotation: auto-revert not written (%s)", type(exc).__name__)
            gen = sha16 = None
        payload = {**self._run_fields(j), "phase": phase, "reason_class": reason,
                   "reverted": reverted, "generation": gen if reverted else None,
                   "registry_sha16": sha16 if reverted else None}
        with contextlib.suppress(Exception):
            self._emit(event, payload, once=False)
        return _Stop(EXIT_FAILED, {"result": event.split(".", 1)[1], "operator_id": j.operator_id,
                                   "phase": phase, "reason_class": reason,
                                   "reverted": reverted, "generation": gen})

    def _abort(self, j: Journal, identity: Identity, phase: str, reason: str) -> _Stop:
        """Before PROMOTE only (design 4.4), acting on LIVE state (kr-r4a
        review fix (b)):

        * the live row's current slot holds the new key -> refuse
          (``failed {internal}``), move the journal forward to PROMOTE, keep
          every key file;
        * ``<key>.prev`` is restored onto the key file only when the live
          row's current hash is sha256(``<key>.prev``);
        * ``next_key`` is removed by editing the LIVE document (the incident
          expiry restored from the pre-publish copy when its row holds the
          same current hash), above the high-water mark, through diff_guard;
        * ``.next`` deleted, ``keyrotation.aborted`` ledgered."""
        if j.phase not in BEFORE_PROMOTE:
            # after PROMOTE there is no rollback, only a forward rotation (4.4)
            return self._fail_kept(j, phase, "internal")
        kp, prev, nxt = Path(identity.key_path), self._key_prev(identity), self._next(identity)
        try:
            live_bytes, live_doc = self._read_live()
        except (OSError, ValueError) as exc:
            log.error("rotation abort: operators file unreadable (%s)", type(exc).__name__)
            return self._fail_kept(j, phase, "internal")
        idx = _row_index(live_doc, j.operator_id)
        row = _rows_of(live_doc)[idx] if idx is not None else None
        live_cur = row.get("key_sha256") if isinstance(row, dict) else None
        if isinstance(live_cur, str) and j.new_fp and live_cur[:16] == j.new_fp:
            # the registry is already promoted: restoring the old key file
            # would lock the identity out (review F2); only forward from here
            log.error("rotation abort refused: %s is already promoted", j.operator_id)
            stop = self._fail_kept(j, phase, "internal")
            self._set_phase(j, POST_PROMOTE_RETRY)
            return stop
        old_sha = key_file_sha(prev)
        if prev.exists():
            if old_sha is None or old_sha[:16] != j.old_fp or live_cur != old_sha:
                # not provably the live current key: keep every file, halt
                log.error("rotation abort refused: %s key .prev is not the live current key",
                          j.operator_id)
                return self._fail_kept(j, phase, "internal")
            if key_file_sha(kp) != old_sha:
                os.replace(str(prev), str(kp))
                _fsync_dir(kp.parent)
            else:
                os.unlink(str(prev))
        self._sweep_links(identity)
        if identity.kind == "daemon" and not self._wait_daemon_fp(identity, j.old_fp):
            log.error("rotation abort: %s did not show its old key again", identity.operator_id)
        reverted, gen, sha16 = False, None, None
        if isinstance(row, dict) and "next_key" in row:
            try:
                candidate = self._header(live_doc, self._next_generation(live_doc))
                rows = [dict(r) for r in _rows_of(candidate)]
                target = rows[idx]
                target.pop("next_key", None)
                self._restore_expiry(target)
                candidate["operators"] = rows
                gen, sha16 = self._publish(live_doc, candidate, [j.operator_id],
                                           save_prev=False, live_bytes=live_bytes)
                reverted = True
                if self._wait_seen(sha16) is not None:
                    log.error("rotation abort: the file without next_key was not seen by "
                              "every service")
            except (OSError, ValueError, PolicyRefused, oa.RegistryUnavailable) as exc:
                log.error("rotation abort: next_key not removed (%s)", type(exc).__name__)
                reverted, gen, sha16 = False, None, None
        with contextlib.suppress(FileNotFoundError):
            os.unlink(str(nxt))
        payload = {**self._run_fields(j), "phase": phase, "reason_class": reason,
                   "reverted": reverted, "generation": gen, "registry_sha16": sha16}
        with contextlib.suppress(Exception):
            self._emit("keyrotation.aborted", payload, once=False)
        self._end_journal(j)
        return _Stop(EXIT_FAILED, {"result": "aborted", "operator_id": j.operator_id,
                                   "phase": phase, "reason_class": reason,
                                   "reverted": reverted, "generation": gen})

    def _restore_expiry(self, target: dict) -> None:
        """design 2.4 item 2 vs invariant 1 (kr-r4a review ruling 6): an
        aborted rotation keeps the original expiry. When the pre-publish copy
        (``rotation/operators.json.prev``) has this row with the SAME current
        hash and no ``next_key``, its ``key_created_at`` / ``key_not_after``
        are put back."""
        try:
            prev_doc = json.loads((self.state / PREV_NAME).read_bytes().decode("utf-8-sig"))
        except (OSError, ValueError):
            return
        pidx = _row_index(prev_doc, target.get("operator_id"))
        if pidx is None:
            return
        prow = _rows_of(prev_doc)[pidx]
        if not isinstance(prow, dict) or prow.get("key_sha256") != target.get("key_sha256") \
                or "next_key" in prow:
            return
        for name in ("key_created_at", "key_not_after"):
            if name in prow:
                target[name] = prow[name]
            else:
                target.pop(name, None)

    @staticmethod
    def _sweep_links(identity: Identity) -> None:
        """kr-r4a review F5: a crash in SWITCH between ``os.link`` and
        ``os.replace`` leaves a hidden ``.<key>.XXXX.link`` hard link to the
        old key; remove any such stray copy."""
        kp = Path(identity.key_path)
        for p in kp.parent.glob(f".{kp.name}.*.link"):
            with contextlib.suppress(OSError):
                os.unlink(str(p))

    # -- the public entry points ---------------------------------------------

    def run_once(self, *, now_id: str | None = None, reason: str = "schedule",
                 dry_run: bool = False) -> tuple[int, dict[str, Any]]:
        """One run. Returns (exit code, content-free summary)."""
        if reason not in ev.START_REASONS:
            return EXIT_USAGE, {"result": "usage", "detail": "unknown reason"}
        if now_id is not None and self.s.identity(now_id) is None:
            return EXIT_USAGE, {"result": "usage", "detail": "identity not managed here"}
        with _umask_077():
            self.state.mkdir(parents=True, exist_ok=True)
            try:
                return self._run(now_id, reason, dry_run)
            except _Stop as stop:
                if not dry_run:
                    with contextlib.suppress(Exception):
                        self._save_status(last_result=stop.summary.get("result"))
                return stop.code, stop.summary
            except Exception as exc:
                log.error("rotation: run failed (%s)", type(exc).__name__)
                return EXIT_FAILED, {"result": "failed", "reason_class": "internal",
                                     "detail": type(exc).__name__}

    def _run(self, now_id: str | None, reason: str, dry_run: bool) -> tuple[int, dict[str, Any]]:
        # 0 PREFLIGHT (O19)
        self._preflight(dry_run)
        # 1 LOCK
        lock = _EstateLock(self.state / LOCK_NAME)
        try:
            lock.acquire()
        except LockHeld:
            if dry_run:
                raise _Stop(EXIT_LOCKED, {"result": "skipped", "skip_reason": "lock"})
            raise self._skip("lock", None, EXIT_LOCKED)
        try:
            return self._locked(now_id, reason, dry_run)
        finally:
            lock.release()

    def _preflight(self, dry_run: bool) -> None:
        if self.e.clock_synced() is not True:
            raise self._skip_or_dry("clock", dry_run, "clock not synchronised")
        try:
            _, live_doc = self._read_live()
        except (OSError, ValueError):
            raise self._skip_or_dry("precheck", dry_run, "operators file unreadable")
        issued = oa.parse_time(live_doc.get("issued_at")) if isinstance(live_doc, dict) else None
        if issued is not None and self.e.now() < issued:
            raise self._skip_or_dry("clock", dry_run, "host clock earlier than issued_at")
        if not self.s.build_sha or self.s.build_sha == "unknown":
            raise self._skip_or_dry("precheck", dry_run, "rotator build sha unknown")
        for svc in self.s.services:
            try:
                sha = self.e.build_sha(svc)
            except EstateError:
                sha = None
            if sha != self.s.build_sha:
                raise self._skip_or_dry("precheck", dry_run, f"build sha differs on {svc}")

    def _skip_or_dry(self, reason: str, dry_run: bool, detail: str) -> _Stop:
        if dry_run:
            return _Stop(EXIT_SKIPPED, {"result": "skipped", "skip_reason": reason,
                                        "detail": detail})
        return self._skip(reason, None, detail=detail)

    def _locked(self, now_id: str | None, reason: str, dry_run: bool) -> tuple[int, dict]:
        live_bytes, live_doc = self._read_live()
        journals, unreadable = self._load_journals()
        if unreadable:
            # review F6: a broken journal halts the estate's rotations (its
            # next_key and key files are where it left them) with an alert
            if dry_run:
                raise _Stop(EXIT_FAILED, {"result": "failed", "reason_class": "internal",
                                          "detail": "a rotation journal is unreadable"})
            oid = unreadable[0] if oa.printable_id(unreadable[0]) else self.s.issued_by
            payload = {"operator_id": oid, "estate": self.s.estate,
                       "run_id": self._new_run_id(), "phase": "precheck",
                       "reason_class": "internal", "reverted": False, "generation": None,
                       "registry_sha16": None}
            with contextlib.suppress(Exception):
                self._emit("keyrotation.failed", payload)
            raise _Stop(EXIT_FAILED, {"result": "failed", "phase": "precheck",
                                      "reason_class": "internal", "operator_id": oid,
                                      "detail": "a rotation journal is unreadable"})
        if journals and not dry_run:
            if now_id is not None and journals[0].operator_id != now_id:
                raise self._skip("lock", now_id, detail="another rotation is in flight")
            return self._resume(journals[0])
        if journals:
            return EXIT_OK, {"result": "dry_run", "would": "resume",
                             "operator_id": journals[0].operator_id, "phase": journals[0].phase}
        self._check_foreign_edit(live_bytes, live_doc, dry_run)
        if (self.state / FREEZE_NAME).exists():
            raise self._skip_or_dry("freeze", dry_run, "rotation.freeze present")
        if _doc_format(live_doc) == 1:
            return self._migrate(live_bytes, live_doc, dry_run)
        identity = self._choose(live_doc, now_id)
        if identity is None:
            return EXIT_OK, {"result": "dry_run" if dry_run else "nothing_due"}
        states = self._precheck(identity, live_bytes, live_doc, dry_run)
        if dry_run:
            return EXIT_OK, {"result": "dry_run", "would": "rotate",
                             "operator_id": identity.operator_id, "reason": reason}
        return self._start(identity, live_doc, reason, states)

    # -- PRECHECK pieces -------------------------------------------------------

    def _check_foreign_edit(self, live_bytes: bytes, live_doc: Any, dry_run: bool,
                            operator_id: str | None = None) -> None:
        st = self._status()
        last, pending = st.get("last_written_sha256"), st.get("pending_sha256")
        sha = sha256_hex(live_bytes)
        if not last:
            # review C-16 finding 2: a lost status file must not switch the
            # detector off. The kept copy of the last file the rotator left
            # in place is the reference; with none kept this is a first run.
            try:
                last = sha256_hex((self.state / PREV_NAME).read_bytes())
            except OSError:
                return
        if sha == last:
            return
        if pending and sha == pending:
            if not dry_run:
                mig = st.get("migration_pending")
                if isinstance(mig, dict):
                    # review C-16 finding 1: a crash after the migration write
                    # still ledgers its generation step, once
                    self._emit("keyrotation.reconciled", {
                        "estate": self.s.estate, "run_id": mig.get("run_id"),
                        "operator_ids": mig.get("operator_ids"),
                        "generation": mig.get("generation"), "registry_sha16": sha[:16]})
                self._save_status(last_written_sha256=sha, pending_sha256=None,
                                  migration_pending=None)
            return
        key_slots_only = False
        with contextlib.suppress(OSError, ValueError, PolicyRefused):
            prev_bytes = (self.state / PREV_NAME).read_bytes()
            if sha256_hex(prev_bytes) == last:
                prev_doc = json.loads(prev_bytes.decode("utf-8-sig"))
                ids = [r.get("operator_id") for r in _rows_of(prev_doc) or []
                       if isinstance(r, dict) and r.get("rotation") != "sealed"]
                probe = dict(live_doc) if isinstance(live_doc, dict) else live_doc
                if isinstance(probe, dict) and _generation(probe) <= _generation(prev_doc):
                    probe["generation"] = _generation(prev_doc) + 1
                diff_guard(prev_doc, probe, [i for i in ids if isinstance(i, str)])
                key_slots_only = True
        if not dry_run:
            self._save_status(foreign_edit={"seen_at": oa.format_time(int(self.e.now())),
                                            "registry_sha16": sha[:16],
                                            "key_slots_only": key_slots_only})
        detail = "the operators file changed outside the rotator"
        if dry_run:
            raise self._skip_or_dry("foreign_edit", dry_run, detail)
        raise self._skip("foreign_edit", operator_id, detail=detail)

    def _choose(self, live_doc: Any, now_id: str | None) -> Identity | None:
        if now_id is not None:
            return self.s.identity(now_id)
        st = self._status()
        last_done = oa.parse_time(st.get("last_completed_at"))
        now = self.e.now()
        if last_done is not None and now < last_done + ESTATE_SPACING_S:
            return None
        best: tuple[float, Identity] | None = None
        for identity in self.s.identities:
            idx = _row_index(live_doc, identity.operator_id)
            if idx is None:
                continue
            row = _rows_of(live_doc)[idx]
            if row.get("status") != "active" or row.get("rotation") != "auto":
                continue
            created = oa.parse_time(row.get("key_created_at"))
            due = (created + ROTATE_EVERY_S + jitter_s(identity.operator_id)
                   if created is not None else float("-inf"))
            if due <= now and (best is None or due < best[0]):
                best = (due, identity)
        return best[1] if best else None

    def _precheck(self, identity: Identity, live_bytes: bytes, live_doc: Any,
                  dry_run: bool) -> dict:
        """design 4.3 step 2."""
        oid = identity.operator_id
        try:
            doc = oa.parse_registry_doc(live_doc, require_active=True)
        except oa.RegistryUnavailable:
            raise self._precheck_fail(oid, dry_run, "the live file does not parse")
        idx = _row_index(live_doc, oid)
        if idx is None:
            raise self._precheck_fail(oid, dry_run, "no row for this identity")
        row = doc.rows[idx]
        if row["status"] != "active" or row["rotation"] != "auto" or row["next_key"] is not None:
            raise self._precheck_fail(oid, dry_run, "row not active/auto or already has next_key")
        cur_sha = key_file_sha(Path(identity.key_path))
        if cur_sha is None or cur_sha != row["key_sha256"]:
            raise self._precheck_fail(oid, dry_run, "key file does not hold the current key")
        for p in (self._next(identity), self._key_prev(identity)):
            if p.exists():
                raise self._precheck_fail(oid, dry_run, "a stale .next/.prev key file exists")
        sha16 = sha256_hex(live_bytes)[:16]
        states = self._states()
        for svc, st in states.items():
            if not isinstance(st, dict) or st.get("registry_sha256_prefix") != sha16 \
                    or st.get("registry_format") != oa.FORMAT_2 \
                    or st.get("last_registry_error") is not None:
                raise self._precheck_fail(oid, dry_run, f"{svc} does not show the host file")
        if identity.kind == "daemon":
            st = states.get(identity.service) or {}
            if st.get("identity_key_fp") != cur_sha[:16]:
                raise self._precheck_fail(oid, dry_run, "daemon does not present the current key")
        return states

    def _precheck_fail(self, oid: str, dry_run: bool, detail: str) -> _Stop:
        if dry_run:
            return _Stop(EXIT_SKIPPED, {"result": "skipped", "skip_reason": "precheck",
                                        "operator_id": oid, "detail": detail})
        return self._skip("precheck", oid, detail=detail)

    # -- migration -------------------------------------------------------------

    def _migrate(self, live_bytes: bytes, live_doc: Any, dry_run: bool) -> tuple[int, dict]:
        now = int(self.e.now())
        states = self._states()
        gen = self._next_generation(live_doc, states)
        try:
            candidate, ids = migration_candidate(live_doc, self.s, now=now, generation=gen)
            diff_guard(live_doc, candidate, [], migration=True)
            oa.parse_registry_doc(candidate, require_active=True)
        except PolicyRefused as exc:
            return self._migration_refused("policy", str(exc), dry_run)
        except oa.RegistryUnavailable as exc:
            return self._migration_refused("validation", str(exc), dry_run)
        if dry_run:
            return EXIT_OK, {"result": "dry_run", "would": "migrate", "rows": len(ids)}
        j = Journal(run_id=self._new_run_id(), operator_id=self.s.issued_by, reason="schedule",
                    started_at=now, phase="publish")
        self._save_status(migration_pending={"run_id": j.run_id, "operator_ids": ids,
                                             "generation": candidate["generation"]})
        try:
            gen, sha16 = self._publish(live_doc, candidate, [], save_prev=True,
                                       live_bytes=live_bytes, migration=True)
        except Exception:
            # refused before the write (a crash, a BaseException, keeps it)
            with contextlib.suppress(Exception):
                self._save_status(migration_pending=None)
            raise
        self._save_status(migration_pending=None)
        reason = self._wait_seen(sha16)
        if reason is not None:
            # ruling 2 / review F3: the migration WAS written; ledger it first
            with contextlib.suppress(Exception):
                self._emit("keyrotation.reconciled", {"estate": self.s.estate,
                                                      "run_id": j.run_id, "operator_ids": ids,
                                                      "generation": gen,
                                                      "registry_sha16": sha16})
            reverted, rsha16 = False, None
            if reason == "registry_error":
                # ruling 7: under ENFORCE a registry_error is a 503 on every
                # guarded call of that service; put the exact pre-migration
                # bytes back (the migration removed no hash, so the
                # retired-hash memory refuses nothing)
                rsha16 = self._restore_format1(live_bytes)
                reverted = rsha16 is not None
            # plain publish_not_seen keeps the format 2 file (R9's
            # --downgrade-format is the path back)
            payload = {**self._run_fields(j), "phase": "publish",
                       "reason_class": reason, "reverted": reverted,
                       "generation": gen if reverted else None,
                       "registry_sha16": rsha16}
            with contextlib.suppress(Exception):
                self._emit("keyrotation.failed", payload, once=False)
            raise _Stop(EXIT_FAILED, {"result": "failed", "phase": "publish",
                                      "reason_class": reason, "reverted": reverted,
                                      "generation": gen})
        self._emit("keyrotation.reconciled", {"estate": self.s.estate, "run_id": j.run_id,
                                              "operator_ids": ids, "generation": gen,
                                              "registry_sha16": sha16})
        self._save_status(last_result="migrated", migrated_at=oa.format_time(now))
        return EXIT_OK, {"result": "migrated", "generation": gen, "rows": len(ids)}

    def _restore_format1(self, original: bytes) -> str | None:
        """Write the exact pre-migration bytes back (no diff_guard: it admits
        format 2 candidates only; these bytes are the file the estate ran on
        before this run). Returns the sha16 written, or None."""
        try:
            kept = (self.state / PREV_NAME).read_bytes()
            if kept != original:
                log.error("rotation: the kept pre-migration copy differs; not restored")
                return None
            self._save_status(pending_sha256=sha256_hex(kept))
            _write_operators(self.ops, kept)
            self._save_status(last_written_sha256=sha256_hex(kept), pending_sha256=None)
        except OSError as exc:
            log.error("rotation: pre-migration bytes not restored (%s)", type(exc).__name__)
            return None
        sha16 = sha256_hex(kept)[:16]
        if self._wait_seen(sha16) is not None:
            log.error("rotation: the restored format 1 file was not seen by every service")
        return sha16

    def _migration_refused(self, reason: str, detail: str, dry_run: bool) -> tuple[int, dict]:
        log.error("rotation: migration refused (%s): %s", reason, detail)
        summary = {"result": "failed", "phase": "publish", "reason_class": reason,
                   "detail": detail}
        if not dry_run:
            payload = {"operator_id": self.s.issued_by, "estate": self.s.estate,
                       "run_id": self._new_run_id(), "phase": "publish",
                       "reason_class": reason, "reverted": False, "generation": None,
                       "registry_sha16": None}
            with contextlib.suppress(Exception):
                self._emit("keyrotation.failed", payload)
        return EXIT_FAILED, summary

    # -- a rotation ------------------------------------------------------------

    def _start(self, identity: Identity, live_doc: Any, reason: str, states: dict) -> tuple[int, dict]:
        idx = _row_index(live_doc, identity.operator_id)
        row = _rows_of(live_doc)[idx]
        self._sweep_links(identity)
        j = Journal(run_id=self._new_run_id(), operator_id=identity.operator_id, reason=reason,
                    started_at=int(self.e.now()), phase="generate",
                    old_fp=fp16(row["key_sha256"]))
        self._save_journal(j)
        self._save_status(in_flight={"operator_id": j.operator_id, "phase": j.phase,
                                     "run_id": j.run_id})
        try:
            self._emit("keyrotation.started", {**self._run_fields(j), "reason": reason,
                                               "old_fp": j.old_fp}, j)
        except Exception:
            # the start could not be ledgered: nothing has been changed yet
            self._end_journal(j)
            raise _Stop(EXIT_FAILED, {"result": "failed", "phase": "precheck",
                                      "reason_class": "io", "operator_id": j.operator_id})
        return self._guarded_advance(j, identity)

    def _resume(self, j: Journal) -> tuple[int, dict]:
        identity = self.s.identity(j.operator_id)
        if identity is None:
            log.error("rotation journal for an identity not managed here: %s", j.operator_id)
            raise _Stop(EXIT_FAILED, {"result": "failed", "reason_class": "internal",
                                      "operator_id": j.operator_id})
        if j.phase in BEFORE_PROMOTE and self.e.now() >= j.started_at + INFLIGHT_LIMIT_S:
            raise self._abort(j, identity, j.phase, "timeout")
        if j.phase not in BEFORE_PROMOTE and j.post_promote_failures >= POST_PROMOTE_MAX_FAILURES:
            raise self._halt_post_promote(j)
        live_bytes, live_doc = self._read_live()
        self._check_foreign_edit(live_bytes, live_doc, False, operator_id=j.operator_id)
        return self._guarded_advance(j, identity)

    def _halt_post_promote(self, j: Journal) -> _Stop:
        """The retry cap (kr-r4a review condition 2): nothing is written; the
        failure is ledgered again each run and logged CRITICAL."""
        log.critical("rotation HALTED: %s failed %d times at or after PROMOTE; both keys and the "
                     "journal are kept, a human or R9 must act", j.operator_id,
                     j.post_promote_failures)
        stop = self._fail_kept(j, j.phase, "internal")
        stop.summary["halted"] = True
        with contextlib.suppress(Exception):
            self._save_status(halted={"operator_id": j.operator_id, "phase": j.phase,
                                      "failures": j.post_promote_failures})
        return stop

    def _guarded_advance(self, j: Journal, identity: Identity) -> tuple[int, dict]:
        """_advance; any unexpected error (a ledger append or a file operation
        that failed) ends the run with everything kept for the next run."""
        try:
            return self._advance(j, identity)
        except _Stop:
            raise
        except Exception as exc:
            log.error("rotation: %s stopped in phase %s (%s); kept for the next run",
                      j.operator_id, j.phase, type(exc).__name__)
            raise _Stop(EXIT_FAILED, {"result": "failed", "operator_id": j.operator_id,
                                      "phase": j.phase, "reason_class": "io",
                                      "reverted": False}) from None

    def _advance(self, j: Journal, identity: Identity) -> tuple[int, dict]:
        steps = [("generate", self._generate), ("publish", self._do_publish),
                 ("verify_next", self._verify_next), ("switch", self._switch),
                 ("confirm_switch", self._confirm_switch), ("soak", self._soak),
                 ("promote", self._promote), ("verify_current", self._verify_current),
                 ("confirm_refused", self._confirm_refused), ("cleanup", self._cleanup)]
        names = [n for n, _ in steps]
        start = names.index(j.phase) if j.phase in names else 0
        for name, fn in steps[start:]:
            if j.phase != name:
                self._set_phase(j, name)
            result = fn(j, identity)
            if result is not None:
                return result
        return EXIT_OK, {"result": "completed", "operator_id": j.operator_id,
                         "old_fp": j.old_fp, "new_fp": j.new_fp,
                         "generation": j.promoted_generation}

    # 3 GENERATE
    def _generate(self, j: Journal, identity: Identity):
        nxt = self._next(identity)
        if nxt.exists():
            sha = key_file_sha(nxt)
            if j.new_fp is not None and sha is not None and sha[:16] == j.new_fp:
                return None
            os.unlink(str(nxt))
        j.new_fp = None
        self._save_journal(j)
        write_new_key(nxt, generate_key())
        self._hook("after_next_written")
        sha = key_file_sha(nxt)
        if sha is None:  # pragma: no cover - our own write
            raise self._abort(j, identity, "generate", "io")
        j.new_fp = fp16(sha)
        self._save_journal(j)
        self._hook("after_generate")
        return None

    # 4 PUBLISH
    def _do_publish(self, j: Journal, identity: Identity):
        new_sha = key_file_sha(self._next(identity))
        live_bytes, live_doc = self._read_live()
        idx = _row_index(live_doc, j.operator_id)
        if idx is None:
            raise self._abort(j, identity, "publish", "foreign_edit")
        row = _rows_of(live_doc)[idx]
        nk = row.get("next_key")
        if new_sha is None or (j.new_fp is not None and new_sha[:16] != j.new_fp):
            # .next lost after a crash: remove a published next_key and start again
            if nk is not None:
                raise self._abort(j, identity, "publish", "io")
            j.phase, j.new_fp = "generate", None
            self._save_journal(j)
            return self._advance(j, identity)
        if nk is not None:
            if nk.get("key_sha256") == new_sha:
                j.published_generation = _generation(live_doc)
                self._save_journal(j)
                return self._emit_published(j, sha256_hex(live_bytes)[:16])
            raise self._abort(j, identity, "publish", "foreign_edit")
        now = int(self.e.now())
        candidate = self._header(live_doc, self._next_generation(live_doc))
        rows = [dict(r) for r in _rows_of(candidate)]
        target = rows[idx]
        target["next_key"] = {"key_sha256": new_sha,
                              "not_before": oa.format_time(now - NOT_BEFORE_SKEW_S),
                              "not_after": oa.format_time(now + KEY_LIFETIME_S)}
        if j.reason == "incident":
            short = now + self._soak_seconds(identity) + INCIDENT_EXTRA_S
            cur = oa.parse_time(target.get("key_not_after"))
            if cur is None or short < cur:
                target["key_not_after"] = oa.format_time(short)
        candidate["operators"] = rows
        try:
            gen, sha16 = self._publish(live_doc, candidate, [j.operator_id], save_prev=True,
                                       live_bytes=live_bytes)
        except PolicyRefused:
            raise self._fail_unwritten(j, identity, "publish", "policy")
        except oa.RegistryUnavailable:
            raise self._fail_unwritten(j, identity, "publish", "validation")
        j.published_generation = gen
        self._save_journal(j)
        self._hook("after_publish")
        reason = self._wait_seen(sha16)
        if reason is not None:
            # review F3: the PUBLISH generation was written; ledger it first
            with contextlib.suppress(Exception):
                self._emit("keyrotation.published", {**self._run_fields(j), "new_fp": j.new_fp,
                                                     "generation": gen,
                                                     "registry_sha16": sha16}, once=False)
            stop = self._revert(j, "publish", reason, event="keyrotation.failed")
            with contextlib.suppress(FileNotFoundError):
                os.unlink(str(self._next(identity)))
            self._end_journal(j)
            raise stop
        return self._emit_published(j, sha16)

    def _emit_published(self, j: Journal, sha16: str):
        self._emit("keyrotation.published", {**self._run_fields(j), "new_fp": j.new_fp,
                                             "generation": j.published_generation,
                                             "registry_sha16": sha16}, j)
        return None

    def _fail_unwritten(self, j: Journal, identity: Identity, phase: str, reason: str) -> _Stop:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(str(self._next(identity)))
        payload = {**self._run_fields(j), "phase": phase, "reason_class": reason,
                   "reverted": False, "generation": None, "registry_sha16": None}
        with contextlib.suppress(Exception):
            self._emit("keyrotation.failed", payload, once=False)
        self._end_journal(j)
        return _Stop(EXIT_FAILED, {"result": "failed", "operator_id": j.operator_id,
                                   "phase": phase, "reason_class": reason, "reverted": False})

    # 5 VERIFY-NEXT
    def _verify_next(self, j: Journal, identity: Identity):
        sha = key_file_sha(self._next(identity))
        if sha is None or not self._verify_all(j.operator_id, sha, "next"):
            raise self._abort(j, identity, "verify_next", "verify_mismatch")
        return None

    # 6 SWITCH
    def _switch(self, j: Journal, identity: Identity):
        kp, prev, nxt = Path(identity.key_path), self._key_prev(identity), self._next(identity)
        live = key_file_sha(kp)
        if live is not None and live[:16] == j.new_fp:
            return None
        if live is None or live[:16] != j.old_fp or key_file_sha(nxt) is None:
            raise self._abort(j, identity, "switch", "io")
        self._sweep_links(identity)
        prev_sha = key_file_sha(prev)
        if prev_sha is None or prev_sha[:16] != j.old_fp:
            tmp = kp.with_name(f".{kp.name}.{secrets.token_hex(4)}.link")
            os.link(str(kp), str(tmp))
            with contextlib.suppress(OSError):
                os.chmod(str(tmp), 0o600)
            os.replace(str(tmp), str(prev))
        self._hook("after_key_prev")
        os.replace(str(nxt), str(kp))
        _fsync_dir(kp.parent)
        self._hook("after_switch")
        return None

    # 7 CONFIRM-SWITCH
    def _confirm_switch(self, j: Journal, identity: Identity):
        if identity.kind == "daemon" and not self._wait_daemon_fp(identity, j.new_fp):
            raise self._abort(j, identity, "confirm_switch", "switch_not_seen")
        result = self._emit("keyrotation.cutover", {**self._run_fields(j), "new_fp": j.new_fp}, j)
        if identity.kind == "self" and self._ledger_mode() != oa.OFF:
            # review F4: in log-only / enforce (or unknown) the cutover append
            # must have authenticated with the NEW key; a missing
            # operator_key_fp means it did not authenticate at all
            payload = result.get("payload") if isinstance(result, dict) else None
            seen = payload.get("operator_key_fp") if isinstance(payload, dict) else None
            if seen != j.new_fp[:8]:
                raise self._abort(j, identity, "confirm_switch", "switch_not_seen")
        if j.soak_started_at is None:
            j.soak_started_at = int(self.e.now())
            self._save_journal(j)
        return None

    def _ledger_mode(self) -> str | None:
        """The sealed ledger's ``operator_mode`` from its rotation-state;
        None when it cannot be read (treated as not off)."""
        try:
            st = self.e.rotation_state("sealed-ledger")
        except EstateError:
            return None
        return st.get("operator_mode") if isinstance(st, dict) else None

    def _soak_seconds(self, identity: Identity) -> int:
        return max(identity.soak_s, MIN_SOAK_S, SOAK_TICKS * self.s.observer_tick_s)

    # 8 SOAK
    def _soak(self, j: Journal, identity: Identity):
        until = (j.soak_started_at or int(self.e.now())) + self._soak_seconds(identity)
        while True:
            if self.e.refusals(j.operator_id, float(j.soak_started_at or j.started_at)) > 0:
                raise self._abort(j, identity, "soak", "refusal_seen")
            if identity.kind == "daemon" and self._daemon_fp(identity) != j.new_fp:
                raise self._abort(j, identity, "soak", "switch_not_seen")
            remaining = until - self.e.now()
            if remaining <= 0:
                return None
            if remaining > self.s.max_wait_s:
                return EXIT_OK, {"result": "in_progress", "operator_id": j.operator_id,
                                 "phase": "soak", "remaining_s": int(remaining)}
            self.e.sleep(min(remaining, float(self.s.observer_tick_s)))

    # 9 PROMOTE
    def _promote(self, j: Journal, identity: Identity):
        live_key = key_file_sha(Path(identity.key_path))
        live_bytes, live_doc = self._read_live()
        idx = _row_index(live_doc, j.operator_id)
        if idx is None or live_key is None or live_key[:16] != j.new_fp:
            raise self._fail_kept(j, "promote", "internal")
        row = _rows_of(live_doc)[idx]
        nk = row.get("next_key")
        if row.get("key_sha256") == live_key and nk is None:
            j.promoted_generation = _generation(live_doc)
            self._save_journal(j)
            return self._emit_retired(j, sha256_hex(live_bytes)[:16])
        if nk is None or nk.get("key_sha256") != live_key:
            raise self._fail_kept(j, "promote", "foreign_edit")
        now = int(self.e.now())
        candidate = self._header(live_doc, self._next_generation(live_doc))
        rows = [dict(r) for r in _rows_of(candidate)]
        target = rows[idx]
        target["key_sha256"] = live_key
        target["key_created_at"] = oa.format_time(now)
        target["key_not_after"] = oa.format_time(now + KEY_LIFETIME_S)
        target.pop("next_key", None)
        candidate["operators"] = rows
        try:
            gen, sha16 = self._publish(live_doc, candidate, [j.operator_id], save_prev=True,
                                       live_bytes=live_bytes)
        except PolicyRefused:
            raise self._fail_kept(j, "promote", "policy")
        except oa.RegistryUnavailable:
            raise self._fail_kept(j, "promote", "validation")
        j.promoted_generation = gen
        self._save_journal(j)
        self._hook("after_promote")
        reason = self._wait_seen(sha16)
        if reason is not None:
            # review F3: the PROMOTE generation was written; ledger it before
            # the revert so every generation step has its event
            with contextlib.suppress(Exception):
                self._emit("keyrotation.retired", {**self._run_fields(j), "old_fp": j.old_fp,
                                                   "generation": gen, "registry_sha16": sha16},
                           once=False)
            stop = self._revert(j, "promote", reason, event="keyrotation.failed")
            # never back to SOAK (review F1, F2): the next run promotes again
            j.emitted = [e for e in j.emitted if e != "keyrotation.retired"]
            j.post_promote_failures += 1
            self._set_phase(j, POST_PROMOTE_RETRY)
            raise stop
        return self._emit_retired(j, sha16)

    def _emit_retired(self, j: Journal, sha16: str):
        self._emit("keyrotation.retired", {**self._run_fields(j), "old_fp": j.old_fp,
                                           "generation": j.promoted_generation,
                                           "registry_sha16": sha16}, j)
        return None

    def _fail_kept(self, j: Journal, phase: str, reason: str) -> _Stop:
        """A failure at or after PROMOTE that wrote nothing: everything is kept
        (both key files, the journal) for the next run."""
        if j.phase not in BEFORE_PROMOTE:
            j.post_promote_failures += 1
            with contextlib.suppress(Exception):
                self._save_journal(j)
        payload = {**self._run_fields(j), "phase": phase, "reason_class": reason,
                   "reverted": False, "generation": None, "registry_sha16": None}
        with contextlib.suppress(Exception):
            self._emit("keyrotation.failed", payload, once=False)
        return _Stop(EXIT_FAILED, {"result": "failed", "operator_id": j.operator_id,
                                   "phase": phase, "reason_class": reason, "reverted": False})

    # 9b VERIFY-CURRENT (O1)
    def _verify_current(self, j: Journal, identity: Identity):
        live_key = key_file_sha(Path(identity.key_path))
        ok = live_key is not None and self._verify_all(j.operator_id, live_key, "current")
        if ok and identity.kind == "daemon":
            ok = self._daemon_fp(identity) == j.new_fp
        if not ok:
            stop = self._revert(j, "verify_current", "verify_mismatch", event="keyrotation.failed")
            # both keys valid again in the re-published .prev (or, if the
            # revert could not be written, the registry stays promoted); the
            # old key file is still there. Never back to SOAK: a 24 h abort
            # would restore the old key against that registry (review F1,
            # F2). The next run promotes again.
            j.emitted = [e for e in j.emitted if e != "keyrotation.retired"]
            j.post_promote_failures += 1
            self._set_phase(j, POST_PROMOTE_RETRY)
            raise stop
        return None

    # 10 CONFIRM-REFUSED
    def _confirm_refused(self, j: Journal, identity: Identity):
        old = key_file_sha(self._key_prev(identity))
        if old is None or old[:16] != j.old_fp:
            raise self._fail_kept(j, "confirm_refused", "io")
        if not self._verify_all(j.operator_id, old, "none"):
            raise self._fail_kept(j, "confirm_refused", "verify_mismatch")
        return None

    # 11 CLEANUP + DONE
    def _cleanup(self, j: Journal, identity: Identity):
        with contextlib.suppress(FileNotFoundError):
            os.unlink(str(self._key_prev(identity)))
        self._sweep_links(identity)
        _write_private(self.state / PREV_NAME, self.ops.read_bytes())
        self._emit("keyrotation.completed", {**self._run_fields(j), "old_fp": j.old_fp,
                                             "new_fp": j.new_fp,
                                             "generation": j.promoted_generation}, j)
        now = oa.format_time(int(self.e.now()))
        st = self._status()
        completed = dict(st.get("completed") or {})
        completed[j.operator_id] = now
        with contextlib.suppress(FileNotFoundError):
            os.unlink(str(self._journal_path(j.operator_id)))
        self._save_status(in_flight=None, completed=completed, last_completed_at=now,
                          last_result="completed")
        return None
