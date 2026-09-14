"""JSONL-backed hash-chained ledger store, with retention by rotation (C2).

ENFORCED: every append links to the previous event's hash; verification
walks every live segment and reports the first break with its segment number
and GLOBAL index. Appends are serialized under an in-process lock AND a
cross-process lock file, and flushed+fsynced before returning.

DECLARED only: append-only-ness of the files themselves. Any process with
write access to the filesystem can rewrite history — the chain guarantees such
tampering is *detectable*, not *impossible*.

Layout (``P`` = the path given, ``D`` = its directory):

- ``P`` is ALWAYS the open segment, whatever its name. A store that never
  rotated is exactly the pre-C2 single file: line n is event n.
- ``D/<stem>-<n><suffix>`` is closed segment n, the old ``P`` renamed by
  ``rotate``. Its successor's first line is a signed, hash-chained
  ``ledger.segment.rotated`` event.
- ``D/<stem>.segments.journal`` is an append-only JSONL state machine
  (``rotate-intent`` before any rename, ``rotate-commit``/``rotate-abort``
  after, ``archive`` before retention moves a closed segment out). Its
  ABSENCE is what makes a store single-file. Closed segments are found only
  through it, never by globbing. It is not tamper-evident: its fields are
  checked against the hash-chained rotation events, and an ``archive`` record
  against the file (still here, or its archive copy) or a hash-chained
  ``ledger.retention.applied`` event.
- ``D/.<name>.lock`` is a 0-byte cross-process writer lock, created by the
  first write. Opening or reading a store creates nothing.
- ``D/legal_hold.json`` is the legal hold: while it exists retention apply
  refuses. Created with O_EXCL (file first, event second), removed by release
  (event first, unlink second), so a crash always leaves the hold in force.
- ``ARCH/<stem>-<n><suffix>`` + ``ARCH/<file>.segment.json`` is an archived
  closed segment and its sidecar (retention apply: sidecar -> journal
  ``archive`` op -> ``os.rename`` outside the lock; same filesystem, never
  overwrite). ``verify_segment_file`` verifies one standalone.

Readers never lock: each read takes a snapshot validated against the journal
bytes and the existence of the two paths a rotation changes (see
``LedgerStore._take_snapshot``). On Windows every read opens files with
FILE_SHARE_DELETE, so a reader in this code never blocks a rotation's rename.
A foreign process holding ``P`` with a plain handle does: rotation then
answers 503 with nothing renamed.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator

from pydantic import BaseModel

from field_core.ledger import (
    GENESIS_HASH,
    ChainVerification,
    LedgerEvent,
    compute_event_hash,
    make_event,
    verify_chain,
)

# Imported at module load, never first under the writer lock: the first import
# of cryptography held the lock ~1 s on the GB10 and 41-46 s on a loaded
# Windows host (C2 build spec trap 9).
from field_core.ledger import flag_signing_failed
from field_core.signing import (
    load_ed25519_private_key,
    load_ed25519_public_key,
    private_key_fingerprint,
    sign_event,
    sign_manifest,
    verify_caller_signature,
    verify_manifest,
)
from sealed_ledger.bundle import ExportSummary, write_bundle
from sealed_ledger.filters import EventFilter, InvalidTimeBound

__all__ = [
    "ArchiveRefused",
    "CallerKeyring",
    "CallerPolicy",
    "CallerRefused",
    "ExportSummary",
    "HoldConflict",
    "InvalidTimeBound",
    "LedgerBusy",
    "LedgerCorrupt",
    "LedgerStore",
    "LegalHoldActive",
    "NoAnchorKey",
    "RotationRefused",
    "RotationResult",
    "SigningConfig",
    "SigningRequired",
    "Snapshot",
    "is_stop_type",
    "load_caller_policy",
    "load_signing_config",
    "verify_segment_file",
]

JOURNAL_FORMAT = "field-ledger-segments/1"
SIDECAR_FORMAT = "field-ledger-segment-sidecar/1"
ROTATION_EVENT_TYPE = "ledger.segment.rotated"
RETENTION_EVENT_TYPE = "ledger.retention.applied"
HOLD_FILE = "legal_hold.json"
CRASH_ENV = "FIELD_LEDGER_CRASH_AT"
READ_CONCURRENCY_ENV = "FIELD_LEDGER_READ_CONCURRENCY"
WRITER_LOCK_TIMEOUT_S = 30.0
#: F2 env var names, spelled once (the store never reads the environment
#: itself; ``sealed_ledger.api.signing_config_from_env`` does).
SIGN_KEY_ENV = "FIELD_LEDGER_SIGN_KEY"
REQUIRE_SIGNING_ENV = "FIELD_LEDGER_REQUIRE_SIGNING"
#: The seal algorithm /health reports (both are field-core SEAL_ALGORITHMS).
SEAL_SIGNED = "ed25519-signed-chain"
SEAL_UNSIGNED = "sha-256-chain"
#: F2 stop-type events: accepted UNSIGNED (stamped ``signing_failed: true``)
#: under FIELD_LEDGER_REQUIRE_SIGNING=1 with no key, because refusing them
#: would keep an agent alive or a token valid. Exactly these (``is_stop_type``).
STOP_EVENT_TYPES = frozenset({"delegation.revoke", "lifecycle.decommissioned"})
STOP_EVENT_PREFIX = "kill."
#: F2b env var names, spelled once (read by ``sealed_ledger.api.caller_policy_from_env``).
CALLER_KEYRING_ENV = "FIELD_LEDGER_CALLER_KEYRING"
REQUIRE_CALLER_SIGNATURE_ENV = "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE"
#: F2b replay window: a claim whose ``caller_ts`` is older than this, or
#: further than the skew into the future, is refused.
CALLER_TS_MAX_AGE_S = 300.0
CALLER_TS_MAX_FUTURE_S = 60.0
#: A caller id names a keyring FILE (``<caller_id>.pub.pem``): the same rule
#: ``keys-admin`` applies to key names, so an id that cannot be imported can
#: never be looked up, and no id reaches outside the keyring directory.
_CALLER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_CALLER_CLAIM_KEYS = ("caller_id", "caller_ts", "caller_signature")
#: F2b: the one log line the caller policy writes (a stop-type append that
#: landed ``caller_unsigned`` with its bad claim dropped); never key material.
log = logging.getLogger("sealed_ledger.store")


class LedgerBusy(RuntimeError):
    """No consistent snapshot, the writer lock, or the rename could not be
    obtained in time (HTTP 503; CLI exit 4). Never evidence of tampering."""


class NoAnchorKey(RuntimeError):
    """Rotation needs a usable signing key; never rotate unsigned (HTTP 503)."""


class SigningRequired(RuntimeError):
    """F2: FIELD_LEDGER_REQUIRE_SIGNING=1 and no per-event signing key is
    loaded — a start-type append (anything but a stop-type event) is refused
    (HTTP 503; CLI exit 2). Nothing is written. Never a process exit."""


def is_stop_type(event_type: str) -> bool:
    """The F2 stop-type classifier, in one place: exactly ``delegation.revoke``,
    every ``kill.<something>`` and ``lifecycle.decommissioned``. Near-misses
    (``kill`` without the dot, ``kill.`` with nothing after it,
    ``lifecycle.decommission``) are start-type."""
    if event_type in STOP_EVENT_TYPES:
        return True
    return event_type.startswith(STOP_EVENT_PREFIX) and len(event_type) > len(STOP_EVENT_PREFIX)


@dataclass(frozen=True)
class SigningConfig:
    """F2 per-event signing as loaded ONCE at store/app start (never a
    process exit). ``private_key_pem`` set = ``signing: on``; ``key_error``
    set = ``signing: error`` (a path was configured, the key is not loadable);
    neither = ``signing: off``. ``require_signing`` is
    FIELD_LEDGER_REQUIRE_SIGNING=1: with no key loaded the ledger is NOT
    appendable for start-type events."""

    # repr=False: a config formatted into any message (repr/str/f-string, a
    # log line, an exception) must never disclose the key (F2 rule 5).
    private_key_pem: str | None = field(default=None, repr=False)
    key_fingerprint: str | None = None  # sha-256 over the raw 32-byte public key
    key_error: str | None = None  # names the failure class, never key material
    require_signing: bool = False

    @property
    def signing(self) -> str:
        if self.private_key_pem is not None:
            return "on"
        return "error" if self.key_error is not None else "off"

    @property
    def appendable(self) -> bool:
        """False exactly when signing is required and no key is loaded."""
        return not (self.require_signing and self.private_key_pem is None)

    @property
    def seal_algorithm(self) -> str:
        return SEAL_SIGNED if self.private_key_pem is not None else SEAL_UNSIGNED

    def health_fields(self) -> dict[str, Any]:
        """The F2 keys of ``GET /health`` (``key_error`` only when ``error``)."""
        out: dict[str, Any] = {
            "appendable": self.appendable, "signing": self.signing,
            "key_fingerprint": self.key_fingerprint, "seal_algorithm": self.seal_algorithm,
            "require_signing": self.require_signing,
        }
        if self.signing == "error":
            out["key_error"] = self.key_error
        return out


def load_signing_config(key_path: str | Path | None, require_signing: bool = False) -> SigningConfig:
    """Load the per-event signing key at ``key_path`` (blank/None = no key
    configured: ``off``). A missing, unreadable or malformed key is
    ``error`` with a one-line ``key_error`` naming the failure class — never
    an exception, never key material. Behaviour then follows
    ``require_signing`` (see ``SigningConfig``)."""
    raw = str(key_path).strip() if key_path is not None else ""
    if not raw:
        return SigningConfig(require_signing=require_signing)
    try:
        pem = Path(raw).read_text(encoding="ascii")
    except (OSError, UnicodeError, ValueError) as exc:
        return SigningConfig(require_signing=require_signing,
                             key_error=f"sign key unreadable ({SIGN_KEY_ENV}): {type(exc).__name__}")
    try:
        load_ed25519_private_key(pem)
        fingerprint = private_key_fingerprint(pem)
    except ValueError as exc:
        return SigningConfig(require_signing=require_signing,
                             key_error=f"sign key unusable ({SIGN_KEY_ENV}): {exc}")
    return SigningConfig(private_key_pem=pem, key_fingerprint=fingerprint,
                         require_signing=require_signing)


# ------------------------------------------------ F2b caller signatures


class CallerRefused(RuntimeError):
    """F2b: a served append's caller claim is refused (HTTP 403): unknown
    caller, invalid signature, ``caller_ts`` outside the replay window,
    incomplete fields, caller fields with no keyring configured, or — under
    FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 — a start-type append with no
    caller fields. Nothing is written. (Under that switch a STOP-type append
    is never refused for any of these: ``CallerPolicy.check``.)"""


class CallerKeyring:
    """``<caller_id>.pub.pem`` files in one directory (GB10: ``/data/keys/callers``
    on the read-only field-keys volume). Files are read on lookup (a key
    imported after the ledger started is seen without a restart) through a
    small mtime/size cache; a file that is not an Ed25519 PUBLIC key makes
    that caller unknown, it never makes the ledger exit."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._cache: dict[str, tuple[int, int, str]] = {}

    def path_for(self, caller_id: str) -> Path | None:
        """The keyring file for an id, or None for an id outside the name rule."""
        if not isinstance(caller_id, str) or not _CALLER_ID.match(caller_id):
            return None
        return self.directory / f"{caller_id}.pub.pem"

    def public_pem(self, caller_id: str) -> str:
        """The PEM text of ``<caller_id>.pub.pem``, checked to be an Ed25519
        public key. ``CallerRefused`` ("unknown caller …") otherwise — the
        message names the id and the failure class, never file contents."""
        path = self.path_for(caller_id)
        if path is None:
            raise CallerRefused(f"unknown caller {caller_id!r}: not a valid caller id")
        try:
            st = os.stat(path)
        except OSError as exc:
            raise CallerRefused(
                f"unknown caller {caller_id!r}: no {path.name} in the keyring ({type(exc).__name__})"
            ) from None
        cached = self._cache.get(caller_id)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
        try:
            pem = path.read_text(encoding="ascii")
            load_ed25519_public_key(pem)
        except (OSError, UnicodeError) as exc:  # unreadable, or not ASCII text
            raise CallerRefused(
                f"unknown caller {caller_id!r}: {path.name} unreadable ({type(exc).__name__})"
            ) from None
        except ValueError as exc:  # load_ed25519_public_key: names the failure class only
            raise CallerRefused(
                f"unknown caller {caller_id!r}: {path.name} is not an Ed25519 public key ({exc})"
            ) from None
        self._cache[caller_id] = (st.st_mtime_ns, st.st_size, pem)
        return pem

    def count(self) -> int:
        """How many ``*.pub.pem`` files the directory holds (0 if unreadable)."""
        try:
            return sum(1 for p in self.directory.iterdir() if p.name.endswith(".pub.pem") and p.is_file())
        except OSError:
            return 0


def _caller_ts_problem(caller_ts: Any, now: datetime) -> str | None:
    """Why ``caller_ts`` is outside the replay window, or None when it is inside."""
    if not isinstance(caller_ts, str):
        return "caller_ts is not a string"
    try:
        ts = datetime.fromisoformat(caller_ts)
    except (TypeError, ValueError):
        return "caller_ts is not an ISO 8601 instant"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts).total_seconds()
    if age > CALLER_TS_MAX_AGE_S:
        return f"caller_ts is {age:.0f} s old (replay window {CALLER_TS_MAX_AGE_S:.0f} s)"
    if -age > CALLER_TS_MAX_FUTURE_S:
        return f"caller_ts is {-age:.0f} s in the future (allowed skew {CALLER_TS_MAX_FUTURE_S:.0f} s)"
    return None


class CallerPolicy:
    """F2b per-append caller verification, loaded ONCE at store/app start.

    ``keyring_dir`` set = ``caller_keyring: on``: a served append carrying
    caller fields is stored only if ``caller_id`` names a keyring file, the
    signature verifies under it and ``caller_ts`` is inside the replay
    window; otherwise the append is refused (403), nothing written. Unset =
    ``off``: caller fields are refused too — an unverifiable claim is never
    stored. ``require_caller_signature`` (FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1):
    a START-type append with no caller fields is refused; a STOP-type one
    (``is_stop_type``) is accepted, stamped ``caller_unsigned: true`` —
    whether it carried no claim or a claim that did not verify (dropped,
    never stored): a stop is never refused by a caller-key fault. The
    ledger's OWN events (hold, retention, rotation) are not served appends
    and are never subject to it."""

    def __init__(self, keyring_dir: str | Path | None = None, require_caller_signature: bool = False):
        self.keyring: CallerKeyring | None = CallerKeyring(keyring_dir) if keyring_dir is not None else None
        self.require_caller_signature = bool(require_caller_signature)

    def __repr__(self) -> str:
        return (f"CallerPolicy(keyring_dir={None if self.keyring is None else str(self.keyring.directory)!r}, "
                f"require_caller_signature={self.require_caller_signature})")

    @property
    def keyring_state(self) -> str:
        return "on" if self.keyring is not None else "off"

    def health_fields(self) -> dict[str, Any]:
        """The F2b keys of ``GET /health``."""
        return {
            "caller_keyring": self.keyring_state,
            "caller_keys": self.keyring.count() if self.keyring is not None else 0,
            "require_caller_signature": self.require_caller_signature,
        }

    def check(self, event_type: str, payload: dict[str, Any] | None, agent_id: str | None,
              claim: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
        """The fields the stored event gains for one served append of
        (``event_type``, ``payload``, ``agent_id``) whose body carried
        ``claim`` (the caller fields, or None): the three verified caller
        fields; ``{"caller_unsigned": True}`` for a stop-type append under
        the require switch that carried no claim OR a claim that did not
        verify (the bad claim is dropped, never stored); or nothing. Raises
        ``CallerRefused`` (nothing written) for every other refusal."""
        if claim is None or all(claim.get(k) is None for k in _CALLER_CLAIM_KEYS):
            if not self.require_caller_signature:
                return {}
            if is_stop_type(event_type):
                return {"caller_unsigned": True}
            raise CallerRefused(
                f"{REQUIRE_CALLER_SIGNATURE_ENV}=1 and the append of '{event_type}' carries no caller "
                "signature (caller_id, caller_ts, caller_signature) — refusing; only stop-type events "
                "(delegation.revoke, kill.*, lifecycle.decommissioned) are accepted without one, "
                "stamped caller_unsigned"
            )
        try:
            return self._verify_claim(event_type, payload, agent_id, claim, now)
        except CallerRefused as exc:
            # F2's principle, applied to caller keys: a stop is never refused
            # by a caller-key fault. Under the require switch a stop-type
            # append whose PRESENTED claim does not verify lands exactly like
            # one that presented none — the claim DROPPED, ``caller_unsigned``
            # stamped. A holder of the perimeter secret can already append
            # that stop-type event with no claim at all, so accepting a bad
            # claim as unsigned is no worse, and refusing it would keep an
            # agent alive. With the switch off (the default) every bad claim
            # on every type is refused: an unverifiable claim is never stored.
            if self.require_caller_signature and is_stop_type(event_type):
                log.warning(
                    "stop-type append of %r landed caller_unsigned under %s=1: its caller claim was "
                    "dropped (%s)", event_type, REQUIRE_CALLER_SIGNATURE_ENV, exc,
                )
                return {"caller_unsigned": True}
            raise

    def _verify_claim(self, event_type: str, payload: dict[str, Any] | None, agent_id: str | None,
                      claim: dict[str, Any], now: datetime | None) -> dict[str, Any]:
        """The three caller fields of a claim that verified; ``CallerRefused``
        naming the fault otherwise — incomplete fields, no keyring, unknown
        caller, ``caller_ts`` outside the replay window, invalid signature
        (the messages name ids and failure classes, never key material)."""
        caller_id, caller_ts, signature = (claim.get(k) for k in _CALLER_CLAIM_KEYS)
        if not all(isinstance(v, str) and v for v in (caller_id, caller_ts, signature)):
            raise CallerRefused(
                "incomplete caller fields: caller_id, caller_ts and caller_signature must all be "
                "present (non-empty strings) or all absent"
            )
        if self.keyring is None:
            raise CallerRefused(
                f"caller keyring not configured ({CALLER_KEYRING_ENV} unset): the claim of caller "
                f"{caller_id!r} cannot be verified here, and an unverifiable claim is never stored"
            )
        pem = self.keyring.public_pem(caller_id)  # raises: unknown caller
        problem = _caller_ts_problem(caller_ts, now or datetime.now(timezone.utc))
        if problem is not None:
            raise CallerRefused(f"caller {caller_id!r} refused: {problem}")
        if not verify_caller_signature(
            {"event_type": event_type, "agent_id": agent_id, "payload": payload or {},
             "caller_id": caller_id, "caller_ts": caller_ts, "caller_signature": signature}, pem
        ):
            raise CallerRefused(
                f"invalid caller signature: the claim of caller {caller_id!r} does not verify under "
                f"{caller_id}.pub.pem over event_type, agent_id, payload, caller_id and caller_ts"
            )
        return {"caller_id": caller_id, "caller_ts": caller_ts, "caller_signature": signature}


def load_caller_policy(keyring_dir: str | Path | None, require_caller_signature: bool = False) -> CallerPolicy:
    """Blank/None = no keyring (``off``). The directory is not opened here: a
    missing one simply makes every caller unknown (``caller_keys: 0``)."""
    raw = str(keyring_dir).strip() if keyring_dir is not None else ""
    return CallerPolicy(Path(raw) if raw else None, require_caller_signature)


def stamp_event(event: LedgerEvent, stamp: dict[str, Any]) -> LedgerEvent:
    """F2b: an UNSIGNED, freshly hashed event with ``stamp``'s fields (caller
    fields, or ``caller_unsigned``) added INSIDE its hash and re-sealed.
    Applied before ``_seal``: hash first, ledger-sign second."""
    if not stamp:
        return event
    if event.signature is not None:
        raise ValueError("a signed event cannot be stamped")
    record = event.model_dump(exclude={"hash", "signature"})
    record.update(stamp)
    return LedgerEvent(**record, hash=compute_event_hash(record))


class RotationRefused(RuntimeError):
    """Nothing to rotate, or the closed segment's name already exists (HTTP 409)."""


class LedgerCorrupt(RuntimeError):
    """The journal or segment files cannot be reconciled without an operator
    (HTTP 500). Readers report the same state as a chain break."""


class HoldConflict(RuntimeError):
    """A legal hold is already in place, or there is none to release (HTTP 409; CLI exit 2)."""


class LegalHoldActive(RuntimeError):
    """Retention apply refused while a legal hold is in place (HTTP 423; CLI exit 4)."""


class ArchiveRefused(RuntimeError):
    """The archive directory breaks a rule, or archival would overwrite a
    file with different content (HTTP 422; CLI exit 2). Nothing is moved."""


class _Retry(Exception):
    """A snapshot attempt saw the layout move; take another."""


# ----------------------------------------------------------- crash test hooks


def _crash_point(name: str) -> None:
    """Die at a named step when FIELD_LEDGER_CRASH_AT names it (tests only;
    inert when the variable is unset)."""
    if os.environ.get(CRASH_ENV) == name:
        os._exit(77)


def _crash_requested(name: str) -> bool:
    return os.environ.get(CRASH_ENV) == name


# -------------------------------------------------------- platform primitives

if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _GENERIC_READ = 0x80000000
    _SHARE_READ_WRITE_DELETE = 0x1 | 0x2 | 0x4
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x80

    def open_shared(path: str | Path) -> BinaryIO:
        """Open for reading WITHOUT blocking a rename or delete of the file.

        A plain ``open()`` on Windows omits FILE_SHARE_DELETE, so while it is
        held ``os.rename`` of the file fails with WinError 32."""
        handle = _kernel32.CreateFileW(
            str(path), _GENERIC_READ, _SHARE_READ_WRITE_DELETE, None,
            _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None,
        )
        if handle == _INVALID_HANDLE:
            err = ctypes.get_last_error()
            if err in (2, 3):
                raise FileNotFoundError(2, f"no such file (winerror {err})", str(path))
            if err in (5, 32, 33, 303):
                raise PermissionError(13, f"open refused (winerror {err})", str(path))
            raise OSError(err, f"CreateFileW failed (winerror {err})", str(path))
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except OSError:
            _kernel32.CloseHandle(handle)
            raise
        return os.fdopen(fd, "rb")

    def fsync_dir(directory: str | Path) -> None:
        """No-op: Windows cannot fsync a directory from Python."""
        return None

    def _try_lock_fd(fd: int) -> bool:
        try:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock_fd(fd: int) -> None:
        os.lseek(fd, 0, 0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def open_shared(path: str | Path) -> BinaryIO:
        """POSIX: a rename never waits on an open handle."""
        return open(path, "rb")

    def fsync_dir(directory: str | Path) -> None:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _try_lock_fd(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock_fd(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def read_shared(path: str | Path) -> bytes | None:
    """The whole file through ``open_shared``, or None if it does not exist."""
    try:
        fh = open_shared(path)
    except FileNotFoundError:
        return None
    with fh:
        return fh.read()


def exists_strict(path: str | Path) -> bool:
    """True/False only when the OS answers; any other error propagates."""
    try:
        os.stat(path)
        return True
    except FileNotFoundError:
        return False


def _parse_events(data: bytes) -> list[LedgerEvent]:
    """Exactly the pre-C2 reader: universal newlines, strip, skip blanks.
    A malformed line raises (JSONDecodeError / ValidationError) as it always did."""
    out: list[LedgerEvent] = []
    for line in io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(LedgerEvent.model_validate(json.loads(line)))
    return out


def _parse_events_located(data: bytes) -> tuple[list[LedgerEvent], tuple[int, str] | None]:
    """``_parse_events`` for verification: the events before the first line
    that does not parse (non-JSON, or not a ledger event), and that line's
    index among the non-blank lines with a one-line reason. Never raises."""
    out: list[LedgerEvent] = []
    for line in io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(LedgerEvent.model_validate(json.loads(line)))
        except ValueError as exc:  # JSONDecodeError and pydantic ValidationError
            lines = [x.strip() for x in str(exc).splitlines() if x.strip()][:3]
            return out, (len(out), f"{type(exc).__name__}: {'; '.join(lines)}"[:300])
    return out, None


def _count_lines_and_last_hash(data: bytes) -> tuple[int, str | None]:
    """Cheap count for /health (no pydantic), same blank-skipping rule."""
    count, last = 0, None
    for raw in data.split(b"\n"):
        if raw.strip():
            count += 1
            last = raw
    head = None
    if last is not None:
        try:
            head = json.loads(last)["hash"]
        except (ValueError, KeyError, TypeError):
            head = None
    return count, head


def _first_line_ts(data: bytes | None) -> str | None:
    if not data:
        return None
    for raw in data.split(b"\n", 64):
        if raw.strip():
            try:
                return json.loads(raw)["ts"]
            except (ValueError, KeyError, TypeError):
                return None
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def journal_path_for(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}.segments.journal")


def closed_path_for(path: str | Path, n: int) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}-{n}{path.suffix}")


def rotating_tmp_for(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(f".{path.name}.rotating")


def writer_lock_path_for(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(f".{path.name}.lock")


def hold_path_for(path: str | Path) -> Path:
    return Path(path).with_name(HOLD_FILE)


def sidecar_path_for(segment_file: str | Path) -> Path:
    """``<file>.segment.json`` beside the segment file (found only by this exact name)."""
    segment_file = Path(segment_file)
    return segment_file.with_name(f"{segment_file.name}.segment.json")


def _sha256_file(path: str | Path) -> str | None:
    """Streamed sha-256 through ``open_shared``; None if the file is absent."""
    digest = hashlib.sha256()
    try:
        fh = open_shared(path)
    except FileNotFoundError:
        return None
    with fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _st_dev(path: str | Path) -> int:
    """The filesystem a path lives on (a seam: tests simulate another one)."""
    return os.stat(path).st_dev


def _within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


# ------------------------------------------------------------------ journal


@dataclass
class JournalState:
    raw: bytes | None
    valid_len: int  # bytes through the last complete line; a torn tail is ignored
    closed: list[dict[str, Any]]  # committed segments in order (archived ones included)
    pending: dict[str, Any] | None  # an intent with no commit/abort yet
    error: str | None


# Every key a reader or writer indexes, per op, with its JSON type. A record
# missing one (or holding the wrong type) is an invalid line — a reported
# break — never a KeyError deep inside a read.
_OP_SCHEMA: dict[str, dict[str, type]] = {
    "rotate-intent": {"format": str, "n": int, "file": str, "start_index": int, "end_index": int,
                      "genesis_prev_hash": str, "head_hash": str, "anchor": dict,
                      "rotation_event": dict},
    "rotate-commit": {"n": int, "rotation_event_hash": str, "closed_at": str},
    "rotate-abort": {"n": int},
    "archive": {"n": int, "file": str, "archived_to": str, "sidecar": str, "sha256": str, "at": str},
}


def _check_record(op: str, rec: dict[str, Any]) -> None:
    for key, kind in _OP_SCHEMA[op].items():
        value = rec.get(key)
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise ValueError(f"{op} field {key!r} missing or not a JSON {kind.__name__}")
    if "file" in rec and (not rec["file"] or Path(rec["file"]).name != rec["file"]):
        raise ValueError(f"{op} file {rec['file']!r} is not a plain file name")
    if op == "rotate-intent" and not isinstance(rec["rotation_event"].get("hash"), str):
        raise ValueError("rotate-intent rotation_event has no hash")


def parse_journal(raw: bytes | None) -> JournalState:
    """``field-ledger-segments/1``. A torn last line (no newline) is ignored;
    any COMPLETE line that fails to parse, lacks a field the op needs, or
    breaks the state machine is a hard error and parsing stops there."""
    if raw is None:
        return JournalState(None, 0, [], None, None)
    closed: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    error: str | None = None
    pos = valid = 0
    chunks = raw.split(b"\n")
    for lineno, chunk in enumerate(chunks[:-1], start=1):  # chunks[-1]: torn tail or b""
        pos += len(chunk) + 1
        text = chunk.strip()
        if not text:
            valid = pos
            continue
        try:
            rec = json.loads(text)
            op = rec["op"]
            if op not in _OP_SCHEMA:
                raise ValueError(f"unknown op {op!r}")
            _check_record(op, rec)
            if op == "rotate-intent":
                if rec.get("format") != JOURNAL_FORMAT:
                    raise ValueError(f"unknown format {rec.get('format')!r}")
                if pending is not None:
                    raise ValueError("second intent while one is pending")
                expected_n = closed[-1]["n"] + 1 if closed else 1
                if rec["n"] != expected_n:
                    raise ValueError(f"intent n={rec['n']} but the next segment is {expected_n}")
                expected_start = closed[-1]["end_index"] + 1 if closed else 0
                if rec["start_index"] != expected_start or rec["end_index"] < rec["start_index"]:
                    raise ValueError("intent indices do not continue the committed segments")
                # a segment starts from the head of the one before it (archived
                # or not): the genesis field is checked here, not only against
                # a rotation event that may itself be archived
                expected_genesis = closed[-1]["head_hash"] if closed else GENESIS_HASH
                if rec["genesis_prev_hash"] != expected_genesis:
                    raise ValueError(
                        f"intent n={rec['n']} genesis_prev_hash does not continue the head of "
                        f"segment {rec['n'] - 1}" if closed else
                        "intent n=1 genesis_prev_hash is not the genesis hash"
                    )
                pending = rec
            elif op in ("rotate-commit", "rotate-abort"):
                if pending is None or rec["n"] != pending["n"]:
                    raise ValueError(f"{op} for n={rec.get('n')} with no matching intent")
                if op == "rotate-commit":
                    if rec["rotation_event_hash"] != pending["rotation_event"]["hash"]:
                        raise ValueError("commit names a different rotation event")
                    closed.append({**pending, "closed_at": rec["closed_at"]})
                pending = None
            elif op == "archive":
                # Retention: the op is journaled BEFORE the file moves, so
                # archived segments are always a prefix of the closed ones.
                if pending is not None:
                    raise ValueError("archive while a rotation is pending")
                live = [c for c in closed if not c.get("archived_to")]
                if not live or rec["n"] != live[0]["n"] or rec.get("file") != live[0]["file"]:
                    raise ValueError(
                        f"archive n={rec.get('n')} is not the oldest live closed segment"
                    )
                live[0].update(
                    archived_to=rec["archived_to"], archived_at=rec["at"],
                    archived_sha256=rec["sha256"], sidecar=rec["sidecar"],
                )
        except Exception as exc:  # noqa: BLE001 - any bad complete line is a hard error
            error = f"segments journal line {lineno} invalid: {exc}"
            break
        valid = pos
    return JournalState(raw, valid, closed, pending, error)


def journal_line(rec: dict[str, Any]) -> bytes:
    return (
        json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


# ---------------------------------------------------------- layout + snapshot


@dataclass
class SegView:
    number: int  # 1-based; the open segment is last closed + 1
    closed: bool
    path: Path
    start_index: int  # global index of the segment's first line
    genesis: str  # prev_hash the segment's first event must carry
    expected_count: int | None = None  # closed only
    expected_head: str | None = None  # closed only
    expected_first_hash: str | None = None  # every segment after a rotation
    must_exist: bool = True
    pred_entry: dict[str, Any] | None = None  # journal entry of the segment before this one


@dataclass
class Layout:
    segmented: bool
    segs: list[SegView]  # live segments in order; the open segment is last
    watch: list[Path]  # the paths a rotation changes: P, and a pending closed name
    journal: JournalState
    error: str | None = None
    archived: list[dict[str, Any]] = field(default_factory=list)


def resolve_layout(
    open_path: Path, js: JournalState, exists: Callable[[Path], bool] = exists_strict
) -> Layout:
    """Pure function of (journal, observed existence).

    ``exists`` MUST be the same memoised observations the caller re-validates:
    deciding "renamed?" from one stat and validating a later one let a rename
    slip between them (under-counts and a false break on Linux, spec trap 1)."""
    if js.raw is None:
        seg = SegView(1, False, open_path, 0, GENESIS_HASH, must_exist=False)
        return Layout(False, [seg], [open_path], js)
    d = open_path.parent
    segs: list[SegView] = []
    watch: list[Path] = [open_path]
    archived: list[dict[str, Any]] = []
    prev_head = GENESIS_HASH
    prev_entry: dict[str, Any] | None = None
    for entry in js.closed:
        if entry.get("archived_to"):
            # Not read. The first live segment's genesis is the archived head,
            # pinned by the rotation event that opens the next segment.
            archived.append(entry)
        else:
            # Committed closed files are immutable and NOT watched: the only
            # legal mover (archival) journals before it moves a file.
            segs.append(SegView(
                entry["n"], True, d / entry["file"], entry["start_index"], prev_head,
                entry["end_index"] - entry["start_index"] + 1, entry["head_hash"],
                expected_first_hash=prev_entry["rotation_event"]["hash"] if prev_entry else None,
                pred_entry=prev_entry,
            ))
        prev_head = entry["head_hash"]
        prev_entry = entry
    open_start = js.closed[-1]["end_index"] + 1 if js.closed else 0
    expected_first = js.closed[-1]["rotation_event"]["hash"] if js.closed else None
    open_must_exist = bool(js.closed)
    segmented = bool(js.closed) or js.error is not None  # a corrupt journal is never "single file"
    pending = js.pending
    if pending is not None:
        renamed_to = d / pending["file"]
        watch.append(renamed_to)
        if exists(renamed_to):
            # R3 happened: segment n is closed; the open file may not exist yet
            segs.append(SegView(
                pending["n"], True, renamed_to, pending["start_index"], prev_head,
                pending["end_index"] - pending["start_index"] + 1, pending["head_hash"],
                expected_first_hash=prev_entry["rotation_event"]["hash"] if prev_entry else None,
                pred_entry=prev_entry,
            ))
            prev_head = pending["head_hash"]
            prev_entry = pending
            open_start = pending["end_index"] + 1
            expected_first = pending["rotation_event"]["hash"]
            open_must_exist = False
            segmented = True
        else:
            open_must_exist = True  # not renamed: P still holds everything
    if segs:
        number = segs[-1].number + 1
    else:
        number = archived[-1]["n"] + 1 if archived else 1
    segs.append(SegView(
        number, False, open_path, open_start, prev_head,
        expected_first_hash=expected_first, must_exist=open_must_exist, pred_entry=prev_entry,
    ))
    return Layout(segmented, segs, watch, js, js.error, archived)


_ENTRY_FIELDS = ("start_index", "end_index", "head_hash", "genesis_prev_hash", "file", "anchor")
_LOCAL_INDEX = re.compile(r"^(link break|hash mismatch) at index (\d+):")


def _verify_segment(
    events: list[LedgerEvent], genesis: str, start_index: int
) -> ChainVerification:
    """``verify_chain(events, genesis)`` with its local index made global.

    ``field_core.verify_chain`` keeps its ``(events, genesis)`` signature, so
    the global offset lives here. With ``start_index == 0`` the result is
    ``verify_chain``'s, unchanged."""
    res = verify_chain(events, genesis)
    if res.ok or start_index == 0:
        return res
    local = res.first_break_index or 0
    reason = _LOCAL_INDEX.sub(
        lambda m: f"{m.group(1)} at index {local + start_index}:", res.reason or "", count=1
    )
    return ChainVerification(
        ok=False, length=res.length + start_index,
        first_break_index=local + start_index, reason=reason,
    )


def _closed_bytes_problem(
    data: bytes, entry: dict[str, Any], genesis: str, sha256: str | None
) -> tuple[int, str] | None:
    """(global index, reason) if ``data`` is not exactly the closed segment the
    journal entry describes: the chain from ``genesis``, the event count, the
    head, and (when journaled at archival) the bytes' sha-256."""
    start, end = entry["start_index"], entry["end_index"]
    try:
        events = _parse_events(data)
    except ValueError as exc:
        return start, f"unparseable line: {exc}"
    res = _verify_segment(events, genesis, start)
    if not res.ok:
        return (start if res.first_break_index is None else res.first_break_index), res.reason or ""
    expected = end - start + 1
    if len(events) != expected:
        return (start + min(len(events), expected),
                f"expected {expected} events (global {start}..{end}), found {len(events)} — "
                "segment truncated or extended")
    if events[-1].hash != entry["head_hash"]:
        return end, (f"head {events[-1].hash[:12]}… does not match the journal's head_hash "
                     f"{entry['head_hash'][:12]}…")
    if sha256 is not None and hashlib.sha256(data).hexdigest() != sha256:
        return start, "file bytes differ from the sha256 journaled at archival"
    return None


def _is_own_inflight(now: tuple, inflight: tuple | None) -> bool:
    """Is the observed disk key the one this store's own in-flight append
    produces? ``inflight`` is the exact expected key or, for an append that
    creates the open segment, ``(("new", sizes), journal_key)``: any inode, a
    size in ``sizes``, the journal unchanged."""
    if inflight is None:
        return False
    if inflight[0] is not None and inflight[0][0] == "new":
        return now[0] is not None and now[0][0] in inflight[0][1] and now[1] == inflight[1]
    return now == inflight


def _journal_vs_rotation_event(entry: dict[str, Any] | None, event: LedgerEvent) -> str | None:
    """The journal is not hash-chained; the rotation event that opens the next
    segment is. Every journal field must agree with it."""
    if entry is None:
        return None
    payload = event.payload
    if event.event_type != ROTATION_EVENT_TYPE or payload.get("segment_closed") != entry["n"]:
        return f"first event is not the rotation event closing segment {entry['n']}"
    bad = [k for k in _ENTRY_FIELDS if payload.get(k) != entry.get(k)]
    if bad:
        return (
            f"journal entry for segment {entry['n']} disagrees with the hash-chained "
            f"rotation event on {', '.join(bad)} (journal edited?)"
        )
    return None


class Snapshot:
    """One consistent read of every live segment (or only the open one)."""

    def __init__(self, layout: Layout, datas: list[bytes | None], attempts: int,
                 parse: bool = True, tolerant: bool = False):
        """``tolerant``: a line that does not parse keeps the events before it
        and is recorded in ``bad`` (segment number -> local index, reason)
        instead of raising — for verification and recovery only; every other
        reader still raises on it."""
        self.layout = layout
        self.attempts = attempts
        self.raw = datas
        self.segments: list[tuple[SegView, list[LedgerEvent] | None]] = []
        self.bad: dict[int, tuple[int, str]] = {}
        if parse:
            for seg, data in zip(layout.segs, datas):
                if data is None:
                    self.segments.append((seg, None))
                elif tolerant:
                    events, bad = _parse_events_located(data)
                    if bad is not None:
                        self.bad[seg.number] = bad
                    self.segments.append((seg, events))
                else:
                    self.segments.append((seg, _parse_events(data)))

    def unparseable(self) -> tuple[int, str] | None:
        """(global index, reason) of the first line that does not parse."""
        for seg, _ in self.segments:
            if seg.number in self.bad:
                local, why = self.bad[seg.number]
                return seg.start_index + local, f"unparseable record at index {seg.start_index + local}: {why}"
        return None

    def all_events(self) -> Iterator[LedgerEvent]:
        """Live events in global order (archived events are not returned)."""
        for _, events in self.segments:
            if events:
                yield from events

    def indexed_events(self) -> Iterator[tuple[int, LedgerEvent]]:
        for seg, events in self.segments:
            for k, event in enumerate(events or ()):
                yield seg.start_index + k, event

    @property
    def global_length(self) -> int:
        length = self.layout.archived[-1]["end_index"] + 1 if self.layout.archived else 0
        for seg, events in self.segments:
            if events is not None:
                length = max(length, seg.start_index + len(events))
            elif seg.closed:
                length = max(length, seg.start_index + (seg.expected_count or 0))
        return length

    @property
    def head(self) -> str | None:
        for _, events in reversed(self.segments):
            if events:
                return events[-1].hash
        return None

    @property
    def earliest_live_index(self) -> int:
        return self.layout.segs[0].start_index

    def archived_entry_for(self, index: int) -> dict[str, Any] | None:
        for entry in self.layout.archived:
            if entry["start_index"] <= index <= entry["end_index"]:
                return entry
        return None

    def hash_at(self, index: int) -> str | None:
        """The hash at a global index, ``"archived"`` if it precedes the live
        segments, or None if no live segment holds it."""
        if index < self.earliest_live_index:
            return "archived"
        for seg, events in self.segments:
            if events and seg.start_index <= index < seg.start_index + len(events):
                return events[index - seg.start_index].hash
        return None

    def verify(self) -> ChainVerification:
        lay = self.layout
        if not lay.segmented:
            events = self.segments[0][1] if self.segments else None
            res = verify_chain(events or [])  # the pre-C2 single-file result, byte for byte
            bad = self.unparseable()
            if res.ok and bad is not None:  # the events before the bad line verified
                return ChainVerification(ok=False, length=bad[0] + 1, first_break_index=bad[0],
                                         reason=bad[1])
            return res
        total = len(lay.segs)
        n_archived = len(lay.archived)
        walked = 0

        def brk(seg: SegView | int, index: int, reason: str) -> ChainVerification:
            number = seg if isinstance(seg, int) else seg.number
            return ChainVerification(
                ok=False, length=index + 1, first_break_index=index,
                reason=f"segment {number}: {reason}", segments=total,
                archived_segments=n_archived, verified_events=walked, break_segment=number,
            )

        found: ChainVerification | None = None
        for seg, events in self.segments:
            if events is None:
                if seg.must_exist:
                    what = (
                        f"{seg.expected_count} events from global index {seg.start_index}"
                        if seg.closed else "the rotation event"
                    )
                    found = brk(seg, seg.start_index,
                                f"file {seg.path.name} is missing (expected {what})")
                    break
                continue
            walked += len(events)
            res = _verify_segment(events, seg.genesis, seg.start_index)
            if not res.ok:
                found = ChainVerification(
                    ok=False, length=res.length, first_break_index=res.first_break_index,
                    reason=f"segment {seg.number}: {res.reason}", segments=total,
                    archived_segments=n_archived, verified_events=walked,
                    break_segment=seg.number,
                )
                break
            bad = self.bad.get(seg.number)
            if bad is not None and (bad[0] == 0 or seg.expected_first_hash is None):
                g = seg.start_index + bad[0]
                found = brk(seg, g, f"unparseable record at index {g}: {bad[1]}")
                break
            if seg.expected_first_hash is not None:
                if not events:
                    found = brk(seg, seg.start_index,
                                "segment is empty — the rotation event is missing")
                    break
                if events[0].hash != seg.expected_first_hash:
                    found = brk(seg, seg.start_index,
                                f"does not start with the recorded rotation event "
                                f"{seg.expected_first_hash[:12]}…")
                    break
                mismatch = _journal_vs_rotation_event(seg.pred_entry, events[0])
                if mismatch:
                    found = brk(seg, seg.start_index, mismatch)
                    break
            if bad is not None:
                g = seg.start_index + bad[0]
                found = brk(seg, g, f"unparseable record at index {g}: {bad[1]}")
                break
            if seg.closed:
                expected = seg.expected_count or 0
                if len(events) != expected:
                    found = brk(
                        seg, seg.start_index + min(len(events), expected),
                        f"expected {expected} events (global {seg.start_index}.."
                        f"{seg.start_index + expected - 1}), found {len(events)} — "
                        "segment truncated or extended",
                    )
                    break
                if events[-1].hash != seg.expected_head:
                    found = brk(
                        seg, seg.start_index + len(events) - 1,
                        f"head {events[-1].hash[:12]}… does not match the journal's "
                        f"head_hash {str(seg.expected_head)[:12]}…",
                    )
                    break
        last = lay.segs[-1]
        if lay.error and (found is None or (found.first_break_index or 0) >= last.start_index):
            # the first segment the journal can no longer describe (build spec
            # §4.4 step 5, after the walk): a real break in an EARLIER segment
            # is reported at its own index; one at or after this point is what
            # the bad journal line would produce, so the line is named instead
            return brk(last, last.start_index, lay.error)
        if found is not None:
            return found
        archived = self._verify_archived()
        if archived is not None:
            return brk(*archived)
        return ChainVerification(
            ok=True, length=self.global_length, segments=total,
            archived_segments=n_archived, verified_events=walked,
        )

    def archive_evidence(self) -> dict[int, set[str]]:
        """Segment number -> every sha-256 a hash-chained
        ``ledger.retention.applied`` event in the LIVE chain names for it
        (payload ``archive_evidence``: ``[{"n": int, "sha256": str}, ...]``).
        The older ``archived_segments`` / ``completed_moves`` lists name no
        digest and are not evidence."""
        named: dict[int, set[str]] = {}
        for _, events in self.segments:
            for event in events or ():
                if event.event_type != RETENTION_EVENT_TYPE:
                    continue
                listed = event.payload.get("archive_evidence")
                for item in listed if isinstance(listed, list) else ():
                    if (isinstance(item, dict) and isinstance(item.get("n"), int)
                            and not isinstance(item.get("n"), bool)
                            and isinstance(item.get("sha256"), str)):
                        named.setdefault(item["n"], set()).add(item["sha256"])
        return named

    def event_evidenced_archives(self) -> dict[int, str]:
        """Archived journal entries (n -> journaled sha-256) that a live
        retention event names with that same digest."""
        named = self.archive_evidence()
        return {
            e["n"]: e["archived_sha256"] for e in self.layout.archived
            if e["archived_sha256"] in named.get(e["n"], ())
        }

    def _verify_archived(self) -> tuple[int, int, str] | None:
        """The journal ``archive`` op is not tamper-evident: an appended line
        drops the oldest live segment from the walk. So (after the live walk)
        EVERY archived journal entry needs its own evidence:

        * its file still in the ledger directory (a pending move) is verified
          like a live closed segment, bytes against the journaled sha-256;
        * otherwise a hash-chained ``ledger.retention.applied`` event in the
          live chain must name that segment number WITH that sha-256 (retention
          apply writes one after its moves, carrying forward every entry an
          earlier live event named);
        * otherwise its archive copy at ``archived_to`` must be present and
          verify (a run killed before its event).

        No entry is excused because a later one is evidenced. Returns
        (segment, global index, reason) for the first entry that fails."""
        lay = self.layout
        if not lay.archived:
            return None
        d = lay.segs[-1].path.parent
        heads = {e["n"]: e["head_hash"] for e in lay.journal.closed}
        evidenced = self.event_evidenced_archives()
        for entry in lay.archived:
            genesis = heads.get(entry["n"] - 1, GENESIS_HASH)
            candidates = [d / entry["file"]]
            if entry["n"] not in evidenced:
                candidates.append(Path(entry["archived_to"]))
            for where in candidates:
                data = read_shared(where)
                if data is None:
                    continue  # moved (only ever D -> archive dir): look at the next place
                problem = _closed_bytes_problem(data, entry, genesis, entry.get("archived_sha256"))
                if problem is not None:
                    index, why = problem
                    return entry["n"], index, f"archived segment ({where.name}): {why}"
                break
            else:
                if entry["n"] not in evidenced:
                    return (
                        entry["n"], entry["start_index"],
                        f"journaled as archived to {entry['archived_to']}, but no "
                        f"{RETENTION_EVENT_TYPE} event in the live chain names it (segment "
                        f"{entry['n']} with sha256 {entry['archived_sha256'][:12]}…) and neither "
                        f"{entry['file']} nor the archive copy is present (journal edited?)",
                    )
        return None


def verify_closed_segment(path: str | Path) -> tuple[dict[str, Any], ChainVerification] | None:
    """Verify ONE closed segment file still in the ledger directory against
    its journal entry.

    The entry is a committed, non-archived one for that file name; or an
    archived one whose file has not moved yet (a pending move: ``state`` is
    ``"pending-move"`` and the bytes must also match the sha-256 journaled at
    archival); or a pending rotation's intent whose rename happened
    (``state`` ``"pending-rotation"``). Returns None when ``path`` is not
    ``<stem>-<n><suffix>`` beside a journal with such an entry. The entry's
    ``genesis_prev_hash`` and ``head_hash`` come from the journal, which is not
    tamper-evident on its own: the full store verify cross-checks them against
    the hash-chained rotation event."""
    path = Path(path)
    m = re.match(r"^(.*)-(\d+)$", path.stem)
    if not m:
        return None
    js = parse_journal(read_shared(path.with_name(f"{m.group(1)}.segments.journal")))
    entry = next(
        (e for e in js.closed if e["file"] == path.name and not e.get("archived_to")), None
    )
    if entry is not None:
        entry = {**entry, "state": "closed"}
    elif exists_strict(path):
        archived = next((e for e in js.closed if e["file"] == path.name), None)
        if archived is not None:
            entry = {**archived, "state": "pending-move"}
        elif js.pending is not None and js.pending["file"] == path.name:
            entry = {**js.pending, "state": "pending-rotation"}
    if entry is None:
        return None
    n, start, end = entry["n"], entry["start_index"], entry["end_index"]
    data = read_shared(path)
    events = _parse_events(data) if data is not None else []

    def brk(index: int, reason: str) -> ChainVerification:
        return ChainVerification(ok=False, length=index + 1, first_break_index=index,
                                 reason=f"segment {n}: {reason}", segments=1,
                                 archived_segments=0, verified_events=len(events),
                                 break_segment=n)

    res = _verify_segment(events, entry["genesis_prev_hash"], start)
    if not res.ok:
        return entry, brk(res.first_break_index or start, res.reason or "")
    expected = end - start + 1
    if len(events) != expected:
        return entry, brk(start + min(len(events), expected),
                          f"expected {expected} events (global {start}..{end}), found "
                          f"{len(events)} — segment truncated or extended")
    if events[-1].hash != entry["head_hash"]:
        return entry, brk(end, f"head {events[-1].hash[:12]}… does not match the journal's "
                               f"head_hash {entry['head_hash'][:12]}…")
    if entry["state"] == "pending-move" and hashlib.sha256(data).hexdigest() != entry["archived_sha256"]:
        return entry, brk(start, "file bytes differ from the sha256 journaled at archival")
    return entry, ChainVerification(ok=True, length=end + 1, segments=1, archived_segments=0,
                                    verified_events=len(events))


_SIDECAR_KEYS = ("format", "logical", "n", "file", "start_index", "end_index",
                 "genesis_prev_hash", "head_hash", "anchor", "closed_at",
                 "closing_rotation_event_hash", "sha256", "archived_by")


def verify_segment_file(path: str | Path, public_key_pem: str | None = None) -> dict[str, Any]:
    """Verify ONE archived segment standalone from ``<file>.segment.json`` beside it.

    Checks the chain from the sidecar's ``genesis_prev_hash`` (break reasons
    carry GLOBAL indices), the event count for ``start_index..end_index``, the
    last hash against ``head_hash`` and the file bytes against ``sha256``.
    Segment 1 must also start at global 0 from the genesis hash.

    The sidecar is unsigned: without ``public_key_pem`` every one of those
    claims is the sidecar's own, and rewriting file and sidecar together
    passes. With the key, the signed rotation anchor must verify and pin
    ``head_hash``, ``chain_length == end_index + 1`` and the segment number,
    so the events back to the claimed genesis are the signer's. The START of
    a segment n > 1 is pinned only by segment n-1's signed head: verify the
    archived segments in order."""
    p = Path(path)
    out: dict[str, Any] = {
        "ok": False, "segment": None, "logical": None, "events": 0, "global_first": None,
        "global_last": None, "reason": None, "signature_checked": False,
    }
    side_raw = read_shared(sidecar_path_for(p))
    if side_raw is None:
        out["reason"] = f"no sidecar {sidecar_path_for(p).name} beside {p}"
        return out
    try:
        side = json.loads(side_raw)
        missing = [k for k in _SIDECAR_KEYS if k not in side]
        if missing or side["format"] != SIDECAR_FORMAT:
            raise ValueError(f"missing {missing}" if missing else f"format {side['format']!r}")
        n, start, end = int(side["n"]), int(side["start_index"]), int(side["end_index"])
    except (ValueError, TypeError, KeyError) as exc:
        out["reason"] = f"sidecar {sidecar_path_for(p).name} invalid: {exc}"
        return out
    out.update(segment=n, logical=side["logical"], global_first=start, global_last=end)

    def fail(reason: str) -> dict[str, Any]:
        out.update(ok=False, reason=f"segment {n}: {reason}")
        return out

    if side["file"] != p.name:
        return fail(f"sidecar describes {side['file']!r}, not {p.name!r}")
    data = read_shared(p)
    if data is None:
        return fail(f"file {p} is missing (expected {end - start + 1} events)")
    try:
        events = _parse_events(data)
    except ValueError as exc:
        return fail(f"unparseable line: {exc}")
    out["events"] = len(events)
    if n == 1 and (start != 0 or side["genesis_prev_hash"] != GENESIS_HASH):
        return fail("segment 1 must start at global index 0 from the genesis hash")
    res = _verify_segment(events, side["genesis_prev_hash"], start)
    if not res.ok:
        return fail(res.reason or "chain break")
    expected = end - start + 1
    if len(events) != expected:
        return fail(f"expected {expected} events (global {start}..{end}), found {len(events)} "
                    "— segment truncated or extended")
    if events[-1].hash != side["head_hash"]:
        return fail(f"head {events[-1].hash[:12]}… does not match the sidecar head_hash "
                    f"{str(side['head_hash'])[:12]}…")
    if hashlib.sha256(data).hexdigest() != side["sha256"]:
        return fail("file bytes differ from the sha256 recorded at archival")
    if public_key_pem is not None:
        anchor = dict(side["anchor"]) if isinstance(side["anchor"], dict) else {}
        signature = anchor.pop("signature", None)
        out["signature_checked"] = True
        try:
            signed = bool(signature) and verify_manifest(anchor, signature, public_key_pem)
        except Exception:  # noqa: BLE001 - a bad key or signature is a failed check
            signed = False
        if not signed:
            return fail("rotation anchor signature does not verify with this public key")
        pinned = (anchor.get("head_hash") == side["head_hash"]
                  and anchor.get("chain_length") == end + 1 and anchor.get("segment") == n)
        if not pinned:
            return fail("signed rotation anchor does not pin this segment's head, "
                        "chain_length and number")
    out.update(ok=True, reason=None)
    return out


class RotationResult(BaseModel):
    segment: int
    file: str
    start_index: int
    end_index: int
    head_hash: str
    rotation_event: LedgerEvent
    anchor: dict[str, Any]  # signed {anchored_at, chain_length, head_hash, segment} — ship it off-box
    rename_attempts: int


@dataclass
class _WriterCache:
    head: str
    global_len: int
    open_start: int
    next_n: int
    closed_head: str
    disk_key: tuple
    pending: bool  # a pending intent, a torn journal tail, or a journal error


def read_concurrency() -> int:
    """FIELD_LEDGER_READ_CONCURRENCY: full-chain parses allowed at once per
    store (default 1; 0 = unlimited). At 100k events one parse peaks at
    ~0.3-0.4 GB and 8 ungated readers at ~2 GB (measured on the GB10): the
    default keeps the ledger inside a 2 GB machine."""
    try:
        return max(0, int(os.environ.get(READ_CONCURRENCY_ENV, "1")))
    except ValueError:
        return 1


def _read_gate() -> threading.BoundedSemaphore | None:
    n = read_concurrency()
    return threading.BoundedSemaphore(n) if n > 0 else None


class LedgerStore:
    SNAPSHOT_TIMEOUT_S = 5.0
    RENAME_RETRIES = 5
    RENAME_RETRY_DELAY_S = 0.1

    def __init__(self, path: str | Path, signing: SigningConfig | None = None,
                 caller: CallerPolicy | None = None):
        """``signing`` (F2): the per-event signing policy this store applies to
        EVERY event it writes (appends, hold and retention events, the
        rotation event). Default: no key, not required — exactly the pre-F2
        behaviour. The served app builds it from the environment once at
        start (``sealed_ledger.api.signing_config_from_env``). ``caller``
        (F2b): the caller-signature policy applied to SERVED appends only
        (``append_for_caller``); default: no keyring, not required."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.signing = signing if signing is not None else SigningConfig()
        self.caller_policy = caller if caller is not None else CallerPolicy()
        self._lock = threading.RLock()  # L0: every write path; re-entrant (rotate -> helpers)
        self._wfd: int | None = None  # L1 fd held by the owning thread, under _lock
        # G: at most N full-chain parses per store at once. Never taken by an
        # append, a rotation or /health. FIELD_LEDGER_READ_CONCURRENCY=0 disables.
        self._gate_sem = _read_gate()
        self.read_concurrency = read_concurrency()  # the served app queues heavy reads to match
        self._journal_cache: tuple[bytes | None, JournalState] | None = None
        self._health_oob: tuple | None = None
        # the disk key this store's own in-flight append will produce: /health
        # must not mistake it for another process's write (C2 J16)
        self._inflight_key: tuple | None = None
        with self._lock:
            self._recover_locked()  # read-only: opening a store never writes

    # ---------------------------------------------------------------- paths

    @property
    def journal_path(self) -> Path:
        return journal_path_for(self.path)

    @property
    def lock_path(self) -> Path:
        return writer_lock_path_for(self.path)

    # ---------------------------------------------------------------- locks

    @contextlib.contextmanager
    def _writer(self):
        """L0 (RLock) then L1 (the lock file). Re-entrant for the owning thread.

        Two LedgerStore instances on one path in the SAME thread must never
        nest writes: the second waits on the first's lock file (30 s, then
        LedgerBusy)."""
        with self._lock:
            if self._wfd is not None:
                yield
                return
            fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
            try:
                deadline = time.monotonic() + WRITER_LOCK_TIMEOUT_S
                while not _try_lock_fd(fd):
                    if time.monotonic() > deadline:
                        raise LedgerBusy(
                            f"ledger busy: writer lock {self.lock_path.name} held by another "
                            f"process for {WRITER_LOCK_TIMEOUT_S:.0f} s"
                        )
                    time.sleep(0.002)
                self._wfd = fd
                try:
                    yield
                finally:
                    self._wfd = None
                    _unlock_fd(fd)
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def _gate(self):
        if self._gate_sem is None:
            yield
            return
        with self._gate_sem:
            yield

    # ------------------------------------------------------------ snapshots

    def _disk_key(self) -> tuple:
        try:
            st = os.stat(self.path)
            open_key = (st.st_size, st.st_ino)
        except FileNotFoundError:
            open_key = None
        try:
            journal_key = os.stat(self.journal_path).st_size
        except FileNotFoundError:
            journal_key = None
        return (open_key, journal_key)

    def _parse_journal_cached(self, raw: bytes | None) -> JournalState:
        cached = self._journal_cache
        if cached is not None and cached[0] == raw:
            return cached[1]
        js = parse_journal(raw)
        self._journal_cache = (raw, js)
        return js

    def _take_snapshot(self, parse: bool = True, open_only: bool = False,
                       tolerant: bool = False) -> Snapshot:
        """The reader protocol (lock-free). Consistent because:

        1. the journal is append-only, so equal bytes before and after mean no
           op landed in between;
        2. within one pending intent only ``P`` and the pending closed name
           change identity, and both are watched with the SAME observations
           the layout was decided from;
        3. the open segment's handle is opened before validation and keeps
           reading the right bytes after a later rename (same inode on POSIX,
           FILE_SHARE_DELETE on Windows);
        4. committed closed files never change; archival journals first;
        5. appends only extend ``P``; a half-copied last line is re-read.
        """
        deadline = time.monotonic() + self.SNAPSHOT_TIMEOUT_S
        delay = 0.0005
        attempts = 0
        torn: list | None = None  # [(size, tail bytes), sightings, first seen]
        journal = self.journal_path
        while True:
            attempts += 1
            handle: BinaryIO | None = None
            try:
                raw1 = read_shared(journal)
                js = self._parse_journal_cached(raw1)
                seen: dict[Path, bool] = {}

                def observe(p: Path) -> bool:
                    if p not in seen:
                        seen[p] = exists_strict(p)
                    return seen[p]

                layout = resolve_layout(self.path, js, observe)
                before = [observe(p) for p in layout.watch]
                # the ONLY handle opened before validation (closed segments are
                # read one at a time afterwards: no EMFILE with many segments)
                try:
                    handle = open_shared(self.path)
                except FileNotFoundError:
                    handle = None
                raw2 = read_shared(journal)
                after = [exists_strict(p) for p in layout.watch]
                if raw2 != raw1 or after != before:
                    raise _Retry("layout changed while opening")
                data_open = handle.read() if handle is not None else None
                if data_open and not data_open.endswith(b"\n"):
                    # Linux extends i_size page by page: an append may be half
                    # copied. Believe a torn last line only after >= 3 identical
                    # sightings over >= 100 ms (then it raises, as it always did).
                    tail = data_open[data_open.rfind(b"\n") + 1:]
                    if tail.strip():
                        try:
                            json.loads(tail)
                        except ValueError:
                            now = time.monotonic()
                            if torn is None or torn[0] != (len(data_open), tail):
                                torn = [(len(data_open), tail), 1, now]
                            else:
                                torn[1] += 1
                            if torn[1] < 3 or now - torn[2] < 0.1:
                                raise _Retry("unterminated last line (append in flight?)")
                datas: list[bytes | None] = [None] * len(layout.segs)
                datas[-1] = data_open
                if not open_only:
                    for k, seg in enumerate(layout.segs[:-1]):
                        data = read_shared(seg.path)
                        if data is None and read_shared(journal) != raw1:
                            raise _Retry("closed segment moved and the journal changed")
                        datas[k] = data
                return Snapshot(layout, datas, attempts, parse=parse, tolerant=tolerant)
            except (_Retry, PermissionError):
                if time.monotonic() > deadline:
                    raise LedgerBusy(
                        f"ledger busy: no consistent snapshot after {attempts} attempts"
                    ) from None
                time.sleep(delay)
                delay = min(delay * 2, 0.05)
            finally:
                if handle is not None:
                    handle.close()

    def snapshot(self) -> Snapshot:
        """A consistent read of every live segment, behind the heavy-read gate."""
        with self._gate():
            return self._take_snapshot()

    # ------------------------------------------------------------- recovery

    def _recover_locked(self) -> None:
        """Refresh the writer cache and the /health tuple (read-only)."""
        for _ in range(100):
            key1 = self._disk_key()
            snap = self._take_snapshot(open_only=True)  # closed counts come from the journal
            key2 = self._disk_key()
            if key1 == key2:
                break
        lay = snap.layout
        closed = [s for s in lay.segs if s.closed]
        if closed:
            closed_head = closed[-1].expected_head or GENESIS_HASH
        elif lay.archived:
            closed_head = lay.archived[-1]["head_hash"]
        else:
            closed_head = GENESIS_HASH
        head = snap.head or closed_head
        glen = snap.global_length
        js = lay.journal
        self._c = _WriterCache(
            head=head, global_len=glen, open_start=lay.segs[-1].start_index,
            next_n=lay.segs[-1].number, closed_head=closed_head, disk_key=key2,
            pending=js.pending is not None or js.error is not None
            or (js.raw is not None and len(js.raw) != js.valid_len),
        )
        self._health = (glen, head, key2, snap.earliest_live_index, self._first_live_ts(snap))

    def _ensure_fresh_locked(self) -> None:
        """First thing under the writer: another writer (process or instance)
        may have appended or rotated since this store last looked."""
        if self._disk_key() != self._c.disk_key or self._c.pending:
            try:
                self._recover_locked()
            except ValueError as exc:  # a line of the open segment no longer parses
                raise LedgerCorrupt(
                    f"open segment {self.path.name} unreadable ({type(exc).__name__}); not writing"
                ) from exc
            if self._c.pending:
                self._reconcile_locked()

    def needs_reconcile(self) -> bool:
        """A pending rotation, a torn journal tail, or a stale rotation tmp."""
        js = parse_journal(read_shared(self.journal_path))
        if js.error:
            return False  # reconcile would refuse; reads report the break
        torn = js.raw is not None and len(js.raw) != js.valid_len
        return js.pending is not None or torn or exists_strict(rotating_tmp_for(self.path))

    def reconcile(self) -> str:
        with self._writer():
            self._recover_locked()
            return self._reconcile_locked()

    def _reconcile_locked(self) -> str:
        """Finish or undo a rotation a crash interrupted. Write paths only:
        never from ``__init__``, a reader, or ``ledger verify``."""
        raw = read_shared(self.journal_path)
        js = parse_journal(raw)
        if js.error:
            raise LedgerCorrupt(js.error)
        outcome = "clean"
        if raw is not None and len(raw) != js.valid_len:
            os.truncate(self.journal_path, js.valid_len)  # a torn record was never acted on
            outcome = "torn-journal-tail-dropped"
        tmp = rotating_tmp_for(self.path)
        pending = js.pending
        if pending is not None:
            renamed_to = self.path.parent / pending["file"]
            if not exists_strict(renamed_to):
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(tmp)
                self._journal_append_locked({
                    "op": "rotate-abort", "n": pending["n"], "at": _now(),
                    "reason": "recovered: crash before rename",
                })
                outcome = "rolled-back"
            else:
                try:
                    closed_events = _parse_events(read_shared(renamed_to) or b"")
                except ValueError as exc:
                    raise LedgerCorrupt(
                        f"pending rotation {pending['n']}: {renamed_to.name} unreadable: {exc}"
                    ) from exc
                expected = pending["end_index"] - pending["start_index"] + 1
                if (len(closed_events) != expected or not closed_events
                        or closed_events[-1].hash != pending["head_hash"]):
                    raise LedgerCorrupt(
                        f"pending rotation {pending['n']}: {renamed_to.name} does not match "
                        "the intent"
                    )
                rot = LedgerEvent.model_validate(pending["rotation_event"])
                if not exists_strict(self.path):
                    self._write_rotating_tmp_locked(rot)
                    self._install_open_segment_locked()
                else:
                    try:
                        first = _parse_events(read_shared(self.path) or b"")[:1]
                    except ValueError as exc:
                        raise LedgerCorrupt(f"open segment unreadable: {exc}") from exc
                    if not first or first[0].hash != rot.hash:
                        raise LedgerCorrupt(
                            f"pending rotation {pending['n']}: the open segment does not "
                            "start with the intended rotation event"
                        )
                self._journal_append_locked({
                    "op": "rotate-commit", "n": pending["n"], "rotation_event_hash": rot.hash,
                    "closed_at": _now(), "recovered": True,
                })
                outcome = "rolled-forward"
        else:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
        self._recover_locked()
        return outcome

    # -------------------------------------------------------- journal/files

    def _journal_append_locked(self, rec: dict[str, Any], torn_crash: str | None = None) -> None:
        """One record: binary, one write loop, fsync (and fsync(D) on create)."""
        path = self.journal_path
        created = not exists_strict(path)
        line = journal_line(rec)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
        try:
            if torn_crash and _crash_requested(torn_crash):
                os.write(fd, line[: len(line) // 2])
                os.fsync(fd)
                os._exit(77)
            view = memoryview(line)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        if created:
            fsync_dir(path.parent)

    def _rename_with_retry(self, src: Path, dst: Path) -> int:
        for attempt in range(1, self.RENAME_RETRIES + 1):
            if exists_strict(dst):  # POSIX rename would silently clobber it
                raise RotationRefused(f"{dst.name} already exists; refusing to overwrite it")
            try:
                os.rename(src, dst)
                return attempt
            except PermissionError:  # Windows WinError 32: a plain handle holds src
                if attempt == self.RENAME_RETRIES:
                    raise
                time.sleep(self.RENAME_RETRY_DELAY_S)
        raise AssertionError("unreachable")

    def _write_rotating_tmp_locked(self, event: LedgerEvent) -> None:
        line = event.model_dump_json() + "\n"
        with open(rotating_tmp_for(self.path), "w", encoding="utf-8") as fh:  # text mode, as append
            if _crash_requested("rotate.segment_tmp_torn"):
                fh.write(line[: len(line) // 2])
                fh.flush()
                os.fsync(fh.fileno())
                os._exit(77)
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def _install_open_segment_locked(self) -> None:
        if exists_strict(self.path):
            raise LedgerCorrupt("open segment reappeared during rotation")
        os.rename(rotating_tmp_for(self.path), self.path)
        fsync_dir(self.path.parent)

    # ----------------------------------------------------------- public API

    @property
    def head_hash(self) -> str:
        """The head as of this store's last recovery or write (a cache)."""
        return self._c.head

    def global_length(self) -> int:
        """The writer's view of the global length (as of the last recovery or
        write). Take a ``snapshot()`` where a consistent (length, head) pair
        is needed."""
        with self._lock:
            return self._c.global_len

    def health_info(self) -> dict[str, Any]:
        """/health: never takes L0, L1 or the read gate; never parses with
        pydantic; never walks closed segments. O(1) (two stats) unless another
        process changed the files, then one lock-free count of the open segment.

        This store's OWN append in flight (written, not yet in the cache) is
        not another process's write: its expected disk key is published before
        the write, so /health answers from the cache while this process appends."""
        for _ in range(3):  # the in-flight key is read BEFORE the cache it precedes
            inflight = self._inflight_key
            count, head, key, earliest, earliest_ts = self._health
            now = self._disk_key()
            own = _is_own_inflight(now, inflight)
            if now == key or own:
                break
        if now != key and not own:
            oob = self._health_oob
            if oob is not None and oob[0] == now:
                count, head, earliest, earliest_ts = oob[1:]
            else:
                try:
                    snap = self._take_snapshot(parse=False, open_only=True)
                    n = snap.layout.archived[-1]["end_index"] + 1 if snap.layout.archived else 0
                    last = snap.layout.archived[-1]["head_hash"] if snap.layout.archived else None
                    for seg, data in zip(snap.layout.segs, snap.raw):
                        if seg.closed:
                            n = seg.start_index + (seg.expected_count or 0)
                            last = seg.expected_head
                        elif data is not None:
                            c, h = _count_lines_and_last_hash(data)
                            n = max(n, seg.start_index + c)
                            last = h or last
                    count, head = n, last or GENESIS_HASH
                    earliest, earliest_ts = snap.earliest_live_index, self._first_live_ts(snap)
                    self._health_oob = (now, count, head, earliest, earliest_ts)
                except Exception:  # noqa: BLE001 - /health answers with the last known values
                    pass
        return {
            "event_count": count, "head_hash": head,
            "earliest_live_index": earliest, "earliest_live_ts": earliest_ts,
        }

    def _first_live_ts(self, snap: Snapshot) -> str | None:
        seg = snap.layout.segs[0]
        data = snap.raw[0]
        if data is None and seg.closed:
            try:
                with open_shared(seg.path) as fh:
                    data = fh.read(65536)
            except OSError:
                data = None
        return _first_line_ts(data)

    def iter_events(self) -> Iterator[LedgerEvent]:
        """Every live event, materialised first: no file handle is held while
        the caller is suspended in the loop."""
        with self._gate():
            events = list(self._take_snapshot().all_events())
        yield from events

    # -------------------------------------------------- F2 signing policy

    def _require_appendable(self, event_type: str) -> None:
        """F2 fail-closed: with FIELD_LEDGER_REQUIRE_SIGNING=1 and no key
        loaded, every START-type event is refused before anything is
        written (``SigningRequired``); a stop-type event passes (it is
        stamped ``signing_failed`` by ``_seal``)."""
        if self.signing.appendable or is_stop_type(event_type):
            return
        raise SigningRequired(
            f"{REQUIRE_SIGNING_ENV}=1 and no per-event signing key is loaded "
            f"({SIGN_KEY_ENV}: {self.signing.key_error or 'unset'}) — refusing to append "
            f"'{event_type}' unsigned; only stop-type events (delegation.revoke, kill.*, "
            "lifecycle.decommissioned) are accepted, stamped signing_failed"
        )

    def _seal(self, event: LedgerEvent) -> LedgerEvent:
        """Apply the signing policy to a freshly hashed event: sign it when a
        key is loaded (hash first, sign second); with signing required and
        no key, a stop-type event is stamped ``signing_failed: true`` (inside
        the hash) and anything else is refused; otherwise it is written
        unsigned, exactly as before F2 (no ``signing_failed`` key)."""
        cfg = self.signing
        if cfg.private_key_pem is not None:
            return sign_event(event, cfg.private_key_pem)
        if not cfg.require_signing:
            return event
        self._require_appendable(event.event_type)  # raises for a start-type event
        return flag_signing_failed(event)

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> LedgerEvent:
        """Append one event as the LEDGER PROCESS itself (the offline CLI, the
        hold, retention and rotation events): no caller fields, and never
        subject to the F2b caller policy — the ledger's own F2 ``signature``
        is what proves the ledger wrote these."""
        return self._append(event_type, payload, agent_id, {})

    def append_for_caller(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        claim: dict[str, Any] | None = None,
    ) -> LedgerEvent:
        """F2b: a SERVED append (``POST /events``). ``claim`` is the body's
        ``caller_id`` / ``caller_ts`` / ``caller_signature`` (None when the
        body carried none). The caller policy runs first, before the writer
        lock — a refusal (``CallerRefused``, HTTP 403) writes nothing; a
        verified claim is stored in the event, inside its hash and under the
        ledger's own signature."""
        stamp = self.caller_policy.check(event_type, payload, agent_id, claim)
        return self._append(event_type, payload, agent_id, stamp)

    def _append(
        self,
        event_type: str,
        payload: dict[str, Any] | None,
        agent_id: str | None,
        stamp: dict[str, Any],
    ) -> LedgerEvent:
        self._require_appendable(event_type)  # before the writer lock: nothing to undo
        with self._writer():
            self._ensure_fresh_locked()
            event = self._seal(stamp_event(make_event(
                event_type=event_type,
                payload=payload,
                prev_hash=self._c.head,
                agent_id=agent_id,
            ), stamp))
            self._append_event_locked(event)
            return event

    def _append_event_locked(self, event: LedgerEvent) -> None:
        line = event.model_dump_json() + "\n"
        prior = self._c.disk_key[0]
        grown = len(line.encode("utf-8")) + len(os.linesep) - 1  # text mode writes os.linesep
        if prior is not None:
            self._inflight_key = ((prior[0] + grown, prior[1]), self._c.disk_key[1])
        else:
            # the open segment does not exist yet (a brand-new ledger, or the
            # first append after a rename whose open file was never installed):
            # this append creates it, so its inode is unknown until it exists,
            # and the empty file between create and write is this append too
            self._inflight_key = (("new", (0, grown)), self._c.disk_key[1])
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
                st = os.fstat(fh.fileno())
            self._c.head = event.hash
            self._c.global_len += 1
            # the journal only changes under L1, which _ensure_fresh_locked checked
            self._c.disk_key = ((st.st_size, st.st_ino), self._c.disk_key[1])
            _, _, _, earliest, earliest_ts = self._health
            self._health = (self._c.global_len, event.hash, self._c.disk_key, earliest,
                            earliest_ts if earliest_ts is not None else event.ts)
        finally:
            self._inflight_key = None  # cleared only AFTER the cache holds the write

    def rotate(self, *, private_key_pem: str | None, operator: str, reason: str) -> RotationResult:
        """Close the open segment by rename (see the module docstring).

        Order: intent (fsync) -> new open segment's tmp (fsync) -> rename P to
        <stem>-<n> -> rename tmp to P -> commit (fsync). A crash at any step
        leaves either the full chain or a reported break, and the next write
        (or served startup) finishes or undoes it. The rotation event (with
        operator, reason and the signed anchor) is the ledger record of the
        rotation; nothing else is appended."""
        if not private_key_pem:
            raise NoAnchorKey("no anchor key configured — refusing an unsigned rotation")
        if not (operator or "").strip() or not (reason or "").strip():
            raise ValueError("rotation needs a non-blank operator and reason")
        self._require_appendable(ROTATION_EVENT_TYPE)  # F2: the rotation event is a start-type append
        with self._writer():
            self._ensure_fresh_locked()
            plan = self._plan_rotation_locked(private_key_pem, operator.strip(), reason.strip())
            _crash_point("rotate.before_intent")
            self._journal_append_locked(plan["intent"], torn_crash="rotate.intent_torn")  # R1
            _crash_point("rotate.after_intent")
            self._write_rotating_tmp_locked(plan["rot"])  # R2
            _crash_point("rotate.segment_tmp_written")
            try:  # R3
                attempts = self._rename_with_retry(self.path, plan["closed"])
            except (PermissionError, RotationRefused) as exc:
                self._journal_append_locked({
                    "op": "rotate-abort", "n": plan["n"], "at": _now(),
                    "reason": f"rename refused: {exc}",
                })
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(rotating_tmp_for(self.path))
                self._refresh_after_abort_locked()
                if isinstance(exc, RotationRefused):
                    raise
                raise LedgerBusy(
                    f"ledger busy: {self.path.name} is held open by another process; "
                    "nothing renamed"
                ) from exc
            fsync_dir(self.path.parent)
            _crash_point("rotate.after_rename")
            self._install_open_segment_locked()  # R4: P = [rotation event]
            _crash_point("rotate.after_segment_created")
            self._journal_append_locked({  # R5
                "op": "rotate-commit", "n": plan["n"], "rotation_event_hash": plan["rot"].hash,
                "closed_at": _now(),
            }, torn_crash="rotate.commit_torn")
            _crash_point("rotate.after_commit")
            self._recover_locked()  # R6
            return RotationResult(
                segment=plan["n"], file=plan["closed"].name, start_index=plan["start"],
                end_index=plan["end"], head_hash=plan["head"], rotation_event=plan["rot"],
                anchor=plan["anchor"], rename_attempts=attempts,
            )

    def _refresh_after_abort_locked(self) -> None:
        """After a refused rename (nothing renamed; the journal gained intent +
        abort) only the journal part of the caches is stale. Refresh that
        instead of ``_recover_locked``, which re-parses the whole open segment
        with pydantic — seconds at 100k events, under both writer locks, while
        every append waits. Anything else changed => the full recovery."""
        key = self._disk_key()
        js = parse_journal(read_shared(self.journal_path))
        if (key[0] != self._c.disk_key[0] or js.pending is not None or js.error is not None
                or (js.raw is not None and len(js.raw) != js.valid_len)):
            self._recover_locked()
            return
        self._c.disk_key = key
        self._c.pending = False
        count, head, _, earliest, earliest_ts = self._health
        self._health = (count, head, key, earliest, earliest_ts)

    def _plan_rotation_locked(self, private_key_pem: str, operator: str, reason: str) -> dict[str, Any]:
        """Everything a rotation writes, computed before its first byte."""
        with self._lock:
            glen = self.global_length()  # re-enters L0
            c = self._c
            n, start, head = c.next_n, c.open_start, c.head
            if glen - start <= 0:
                raise RotationRefused("open segment is empty; nothing to rotate")
            closed = closed_path_for(self.path, n)
            if exists_strict(closed):
                raise RotationRefused(f"{closed.name} already exists; refusing to overwrite it")
            record = {"anchored_at": _now(), "chain_length": glen, "head_hash": head, "segment": n}
            anchor = {**record, "signature": sign_manifest(record, private_key_pem)}
            # F2: the rotation event is an event of the chain like any other,
            # so it carries the per-event signature when a key is loaded (the
            # anchor above is signed with the SEPARATE anchor key).
            rot = self._seal(make_event(
                ROTATION_EVENT_TYPE,
                payload={
                    "segment_closed": n, "file": closed.name, "start_index": start,
                    "end_index": glen - 1, "head_hash": head, "genesis_prev_hash": c.closed_head,
                    "anchor": anchor, "operator": operator, "reason": reason,
                },
                prev_hash=head,
            ))
            intent = {
                "op": "rotate-intent", "format": JOURNAL_FORMAT, "n": n, "file": closed.name,
                "start_index": start, "end_index": glen - 1, "genesis_prev_hash": c.closed_head,
                "head_hash": head, "anchor": anchor, "rotation_event": rot.model_dump(),
                "at": _now(),
            }
            return {"n": n, "start": start, "end": glen - 1, "head": head, "closed": closed,
                    "anchor": anchor, "rot": rot, "intent": intent}

    def events(
        self,
        agent_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[LedgerEvent]:
        """Filtered read of the live segments in global order. ``since``/``until``
        are inclusive ISO 8601 instants (compared as datetimes, not strings); a
        bad bound raises ``InvalidTimeBound`` before anything is read. ``limit``
        keeps the last N matches globally."""
        event_filter = EventFilter(
            agent_id=agent_id, event_type=event_type, since=since, until=until
        )
        with self._gate():
            snap = self._take_snapshot()
        out = [event for index, event in snap.indexed_events() if event_filter.matches(index, event)]
        if limit is not None:
            out = out[-limit:]
        return out

    def verify(self) -> ChainVerification:
        try:
            with self._gate():
                return self._take_snapshot(tolerant=True).verify()
        except LedgerBusy as exc:
            return ChainVerification(ok=False, length=0, reason=str(exc))

    def hash_at(self, index: int) -> str | None:
        with self._gate():
            return self._take_snapshot().hash_at(index)

    def export(
        self,
        out_dir: str | Path,
        *,
        since: str | None = None,
        until: str | None = None,
        agent_id: str | None = None,
        event_type: str | None = None,
        private_key_pem: str | None = None,
    ) -> ExportSummary:
        """Auditor export bundle ``out_dir/<stamp>/`` (see ``sealed_ledger.bundle``).

        The live chain is read ONCE (one snapshot); the filters, the spine,
        ``head_hash`` and the verification all come from that read (never
        from the cached head). Indices are global: a ledger whose oldest
        segments are archived exports from ``earliest_live_index``.
        ``private_key_pem`` signs summary + chain_proof; the served route
        never passes one.
        """
        event_filter = EventFilter(
            agent_id=agent_id, event_type=event_type, since=since, until=until
        )
        with self._gate():
            snap = self._take_snapshot()
            events = list(snap.all_events())
            verification = snap.verify()
        return write_bundle(
            out_dir, events, event_filter, private_key_pem=private_key_pem,
            verification=verification, start_index=snap.earliest_live_index,
        )

    # ------------------------------------------------------------ legal hold

    @property
    def hold_path(self) -> Path:
        return hold_path_for(self.path)

    def hold_status(self) -> dict[str, Any] | None:
        """The hold record, or None when no hold is in place. The file's
        EXISTENCE is the hold: an unparseable marker (a crash between create
        and write) is still a hold."""
        raw = read_shared(self.hold_path)
        if raw is None:
            return None
        try:
            rec = json.loads(raw)
        except ValueError:
            rec = None
        if not isinstance(rec, dict):
            return {"placed_at": None, "placed_by": None,
                    "reason": f"unparseable hold marker ({len(raw)} bytes)"}
        return rec

    def _hold_text(self) -> str:
        return json.dumps(self.hold_status(), sort_keys=True, ensure_ascii=False)

    def place_hold(self, *, by: str, reason: str) -> dict[str, Any]:
        """Place the legal hold. The FILE is written (O_EXCL, fsync) before the
        ``ledger.legal_hold.placed`` event: a crash between them leaves the hold
        in force, without its event."""
        by, reason = (by or "").strip(), (reason or "").strip()
        if not by or not reason:
            raise ValueError("a legal hold needs a non-blank --by and --reason")
        self._require_appendable("ledger.legal_hold.placed")  # F2: before the marker is written
        with self._writer():
            rec = {"placed_at": _now(), "placed_by": by, "reason": reason}
            try:
                fd = os.open(self.hold_path,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
            except FileExistsError:
                raise HoldConflict(f"a legal hold is already in place: {self._hold_text()}") from None
            try:
                view = memoryview((json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            fsync_dir(self.hold_path.parent)
            _crash_point("hold.file_written")
            try:
                self.append("ledger.legal_hold.placed", rec)
            except (LedgerBusy, LedgerCorrupt) as exc:
                raise type(exc)(
                    f"the legal hold IS in place ({self.hold_path.name} written) but its "
                    f"ledger event failed: {exc}"
                ) from exc
            return rec

    def release_hold(self, *, by: str) -> dict[str, Any]:
        """Release the legal hold. The ``ledger.legal_hold.released`` event is
        written BEFORE the file is removed: a crash between them leaves the hold
        in force (a second release then records a second event)."""
        by = (by or "").strip()
        if not by:
            raise ValueError("releasing a legal hold needs a non-blank --by")
        with self._writer():
            held = self.hold_status()
            if held is None:
                raise HoldConflict("no legal hold is in place")
            rec = {**held, "released_by": by, "released_at": _now()}
            self.append("ledger.legal_hold.released", rec)
            _crash_point("hold.event_first")
            for attempt in range(1, 51):
                try:
                    os.unlink(self.hold_path)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:  # Windows: a plain handle holds the marker
                    if attempt == 50:
                        raise LedgerBusy(
                            f"ledger busy: the release event is written but {self.hold_path.name} "
                            "is held open by another process — the hold is STILL in force; retry"
                        ) from None
                    time.sleep(0.02)
            fsync_dir(self.hold_path.parent)
            return rec

    # ------------------------------------------------------- retention apply

    def retention_state(self) -> dict[str, Any]:
        """Cheap state for ``/retention/check``: the journal, the hold marker and
        the /health cache. Never parses an event and never takes a lock."""
        js = parse_journal(read_shared(self.journal_path))
        archived = [e for e in js.closed if e.get("archived_to")]
        health = self.health_info()
        return {
            "earliest_live_index": health["earliest_live_index"],
            "earliest_live_ts": health["earliest_live_ts"],
            "segments": len(js.closed) - len(archived) + 1,
            "archived_segments": len(archived),
            "pending_moves": self._pending_moves(js),
            "legal_hold": self.hold_status(),
        }

    def archive_closed_segments(
        self,
        *,
        older_than_days: float,
        archive_dir: str | Path,
        operator: str,
        allow_external: bool = False,
        data_dir: str | Path | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Retention apply: move CLOSED segments whose ``closed_at`` is more than
        ``older_than_days`` old to ``archive_dir``, oldest first, never the open
        segment. Archived segments stay a prefix: the first segment that is too
        young stops the run.

        Refused (``ArchiveRefused``, nothing moved) when ``archive_dir`` is the
        live ledger directory or inside it, outside ``data_dir``
        (``FIELD_DATA_DIR``) unless ``allow_external``, or on another
        filesystem (archival renames, it never copies). ``LegalHoldActive``
        while ``legal_hold.json`` exists, checked again under the writer lock.

        Per segment (G6): verify it against the journal and the rotation event
        that opens its successor (read-only, behind the read gate) -> write the
        sidecar -> journal ``archive`` op under both writer locks (COMMIT:
        readers stop opening the file) -> ``os.rename`` outside the locks,
        never overwriting. A file another process holds (Windows) is left as a
        PENDING move that the next apply completes. Idempotent: with nothing
        to do nothing is written, no event included.

        Before its first commit (or pending move) a run verifies the whole live
        chain and refuses (``LedgerCorrupt``) if it breaks, so it never
        archives past a forged journal record. A run refused after it archived
        something still appends ``ledger.retention.applied`` for what it did
        (with ``error``), and removes a sidecar it wrote for a segment it did
        not commit."""
        operator = (operator or "").strip()
        if not operator:
            raise ValueError("retention apply needs a non-blank operator")
        if older_than_days < 0:
            raise ValueError("--days must be >= 0")
        self._require_appendable(RETENTION_EVENT_TYPE)  # F2: before anything moves
        now = now or datetime.now(timezone.utc)
        adir = Path(archive_dir).resolve()
        ldir = self.path.parent.resolve()
        if _within(adir, ldir):
            raise ArchiveRefused(f"archive dir {adir} is inside the live ledger dir {ldir}")
        droot = Path(data_dir if data_dir is not None
                     else os.environ.get("FIELD_DATA_DIR", "./var")).resolve()
        if not allow_external and not _within(adir, droot):
            raise ArchiveRefused(
                f"archive dir {adir} is outside FIELD_DATA_DIR {droot} (use --allow-external)"
            )
        if exists_strict(self.hold_path):
            raise LegalHoldActive(f"legal hold in place: {self._hold_text()}")
        adir.mkdir(parents=True, exist_ok=True)
        if _st_dev(adir) != _st_dev(ldir):
            raise ArchiveRefused(
                f"archive dir {adir} is on a different filesystem than {ldir}; archival "
                "renames, it never copies"
            )
        cutoff = now - timedelta(days=older_than_days)
        completed: list[int] = []
        archived: list[int] = []
        # archive_evidence for this run's event: entries a live retention event
        # already named (carried forward from the verified snapshot) plus the
        # segments THIS run commits. A pending move this run only completes,
        # or an entry evidenced only by its bytes, is never promoted to event
        # evidence: nothing here can tell it from a forged archive line.
        evidence: dict[int, str] = {}
        verified = False
        try:
            if self._pending_moves():
                evidence.update(self._refuse_unless_live_verify_ok())
                verified = True
            completed = self._complete_pending_moves()
            while True:
                plan = self._plan_archive(adir, cutoff, operator)
                if plan is None:
                    break
                if plan == "replan":
                    continue
                if not verified:  # once per run, before this run commits anything
                    evidence.update(self._refuse_unless_live_verify_ok())
                    verified = True
                entry, seg_path, dst, sidecar, digest, side = plan
                if exists_strict(self.hold_path):  # before writing anything for this segment
                    raise LegalHoldActive(f"legal hold in place: {self._hold_text()}")
                created = self._write_sidecar(sidecar, side)
                _crash_point("archive.sidecar_written")
                with self._writer():
                    self._ensure_fresh_locked()
                    js = parse_journal(read_shared(self.journal_path))
                    refusal: Exception | None = None
                    if exists_strict(self.hold_path):
                        refusal = LegalHoldActive(f"legal hold in place: {self._hold_text()}")
                    elif js.error:
                        refusal = LedgerCorrupt(js.error)
                    if refusal is not None:
                        # never leave a sidecar for a segment this run did not commit
                        # (it would block another operator's apply)
                        committed = any(e["n"] == entry["n"] and e.get("archived_to") for e in js.closed)
                        if created and not committed:
                            with contextlib.suppress(OSError):
                                os.unlink(sidecar)
                        raise refusal
                    live = [c for c in js.closed if not c.get("archived_to")]
                    if js.pending is not None or not live or live[0] != entry:
                        continue  # the journal moved under us: plan again
                    self._journal_append_locked({
                        "op": "archive", "n": entry["n"], "file": entry["file"],
                        "archived_to": str(dst), "sidecar": str(sidecar), "sha256": digest,
                        "at": _now(), "operator": operator,
                    }, torn_crash="archive.op_torn")
                    _crash_point("archive.committed")
                    self._recover_locked()
                archived.append(entry["n"])
                evidence[entry["n"]] = digest
                self._move_one(seg_path, dst, digest)
                _crash_point("archive.moved")
        except Exception as exc:
            # A refusal after this run archived something still ledgers what it
            # did (only a killed process leaves an archival with no event).
            if archived or completed:
                try:
                    self._retention_event(older_than_days, adir, archived, completed, operator,
                                          evidence, error=f"{type(exc).__name__}: {exc}"[:500])
                except Exception as event_exc:  # noqa: BLE001 - the refusal is what the caller sees
                    exc.add_note(f"its {RETENTION_EVENT_TYPE} event also failed: {event_exc}")
            raise
        pending = self._pending_moves()
        result: dict[str, Any] = {
            "archived_segments": archived, "completed_moves": completed,
            "pending_moves": pending, "archive_dir": str(adir), "retention_event_hash": None,
        }
        if archived or completed:
            event = self._retention_event(older_than_days, adir, archived, completed, operator,
                                          evidence)
            result["retention_event_hash"] = event.hash
        return result

    def _retention_event(self, older_than_days: float, adir: Path, archived: list[int],
                         completed: list[int], operator: str, evidence: dict[int, str],
                         error: str | None = None) -> LedgerEvent:
        payload: dict[str, Any] = {
            "older_than_days": older_than_days, "archive_dir": str(adir),
            "archived_segments": archived, "completed_moves": completed,
            "pending_moves": self._pending_moves(), "operator": operator,
            "archive_evidence": [{"n": n, "sha256": evidence[n]} for n in sorted(evidence)],
        }
        if error is not None:
            payload["error"] = error
        return self.append(RETENTION_EVENT_TYPE, payload)

    def _refuse_unless_live_verify_ok(self) -> dict[int, str]:
        """Retention apply never archives past a ledger whose live verify
        breaks: archiving the next segment would otherwise hide an earlier
        break (a forged ``archive`` op above all) behind a genuine
        ``ledger.retention.applied`` event. Returns the archived entries a
        live retention event names with their journaled sha-256 (what this
        run's event carries forward)."""
        with self._gate():
            snap = self._take_snapshot(tolerant=True)
            v = snap.verify()
        if v.ok:
            return snap.event_evidenced_archives()
        reason = v.reason or "chain break"
        if v.break_segment is None:
            raise LedgerCorrupt(f"live verify reports a break; not archiving ({reason})")
        prefix = f"segment {v.break_segment}: "
        if reason.startswith(prefix):
            reason = reason[len(prefix):]
        raise LedgerCorrupt(
            f"segment {v.break_segment} does not verify against the journal; not archived ({reason})"
        )

    def _plan_archive(self, adir: Path, cutoff: datetime, operator: str):
        """The next segment to archive and everything its sidecar says, verified.
        None = nothing (more) to archive; "replan" = the journal moved."""
        with self._gate():
            snap = self._take_snapshot(parse=False, open_only=True)
            lay = snap.layout
            if lay.error:
                raise LedgerCorrupt(f"not archiving: {lay.error}")
            committed = {e["n"]: e for e in lay.journal.closed if not e.get("archived_to")}
            if len(lay.segs) < 2 or not lay.segs[0].closed or lay.segs[0].number not in committed:
                return None  # no committed live closed segment (the open one is never archived)
            seg, successor = lay.segs[0], lay.segs[1]
            entry = committed[seg.number]
            try:
                closed_at = datetime.fromisoformat(entry["closed_at"])
            except (TypeError, ValueError) as exc:
                raise LedgerCorrupt(f"segment {seg.number}: closed_at unreadable: {exc}") from exc
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            if closed_at >= cutoff:
                return None
            data = read_shared(seg.path)
            if data is None:
                if read_shared(self.journal_path) != lay.journal.raw:
                    return "replan"
                raise LedgerCorrupt(f"segment {seg.number}: {seg.path.name} is missing; not archived")

            def refuse(why: str) -> LedgerCorrupt:
                return LedgerCorrupt(
                    f"segment {seg.number} does not verify against the journal; not archived ({why})"
                )

            try:
                events = _parse_events(data)
            except ValueError as exc:
                raise refuse(f"unparseable line: {exc}") from exc
            res = _verify_segment(events, seg.genesis, seg.start_index)
            if not res.ok:
                raise refuse(res.reason or "chain break")
            if len(events) != seg.expected_count or events[-1].hash != seg.expected_head:
                raise refuse(f"expected {seg.expected_count} events ending in "
                             f"{str(seg.expected_head)[:12]}…, found {len(events)}")
            # The sidecar copies the journal entry, which is not tamper-evident on
            # its own: require the hash-chained rotation event that opens the
            # successor to agree with it first. The successor may be the open
            # segment, which a concurrent rotation renames — but only after its
            # intent is journaled, so a changed journal means "plan again".
            first = self._first_event(successor.path)
            if first is None:
                problem = f"the successor {successor.path.name} has no rotation event"
            elif first.hash != entry["rotation_event"]["hash"]:
                problem = f"{successor.path.name} does not start with the recorded rotation event"
            else:
                problem = _journal_vs_rotation_event(entry, first)
            if problem:
                if read_shared(self.journal_path) != lay.journal.raw:
                    return "replan"
                raise refuse(problem)
        digest = hashlib.sha256(data).hexdigest()
        dst = adir / entry["file"]
        existing = _sha256_file(dst)
        if existing is not None and existing != digest:
            raise ArchiveRefused(f"{dst} already exists with different content; refusing to overwrite it")
        side = {
            "format": SIDECAR_FORMAT, "logical": self.path.name,
            **{k: entry[k] for k in ("n", "file", "start_index", "end_index",
                                     "genesis_prev_hash", "head_hash", "anchor", "closed_at")},
            "closing_rotation_event_hash": entry["rotation_event"]["hash"],
            "sha256": digest, "archived_by": operator,
        }
        return entry, seg.path, dst, sidecar_path_for(dst), digest, side

    def _first_event(self, path: Path) -> LedgerEvent | None:
        try:
            fh = open_shared(path)
        except FileNotFoundError:
            return None
        with fh:
            line = fh.readline()
        try:
            return LedgerEvent.model_validate(json.loads(line)) if line.strip() else None
        except ValueError:
            return None

    def _write_sidecar(self, sidecar: Path, side: dict[str, Any]) -> bool:
        """tmp -> fsync -> target-absent check -> rename -> fsync(dir). An existing
        sidecar with identical content is accepted (a re-run); a different one
        refuses (it is never overwritten). True when this call created it."""
        existing = read_shared(sidecar)
        if existing is not None:
            try:
                same = json.loads(existing) == side
            except ValueError:
                same = False
            if not same:
                raise ArchiveRefused(
                    f"{sidecar} exists with different content (an uncommitted earlier attempt by "
                    "another operator?); refusing to overwrite it"
                )
            return False
        tmp = sidecar.with_name(f".{sidecar.name}.tmp")
        with open(tmp, "wb") as fh:
            fh.write((json.dumps(side, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if exists_strict(sidecar):
            os.unlink(tmp)
            raise ArchiveRefused(f"{sidecar} appeared during archival; refusing to overwrite it")
        os.rename(tmp, sidecar)
        fsync_dir(sidecar.parent)
        return True

    def _move_one(self, src: Path, dst: Path, digest: str) -> str:
        """done | pending (a handle holds src) | conflict (dst differs: never
        overwritten) | missing."""
        for _attempt in range(self.RENAME_RETRIES):
            if exists_strict(dst):
                if not exists_strict(src):
                    return "done"
                if _sha256_file(dst) != digest:
                    return "conflict"
                try:  # an earlier move copied nothing: dst IS src's bytes; drop src
                    os.unlink(src)
                    fsync_dir(src.parent)
                    return "done"
                except FileNotFoundError:
                    return "done"
                except PermissionError:
                    time.sleep(self.RENAME_RETRY_DELAY_S)
                    continue
            try:
                os.rename(src, dst)
                fsync_dir(dst.parent)
                fsync_dir(src.parent)
                return "done"
            except FileNotFoundError:
                return "done" if exists_strict(dst) else "missing"
            except PermissionError:  # Windows: a plain handle holds src
                time.sleep(self.RENAME_RETRY_DELAY_S)
        return "pending"

    def _pending_moves(self, js: JournalState | None = None) -> list[dict[str, Any]]:
        """Archived in the journal, file still in the live directory."""
        js = js if js is not None else parse_journal(read_shared(self.journal_path))
        return [
            {"n": e["n"], "file": e["file"], "archived_to": e["archived_to"]}
            for e in js.closed
            if e.get("archived_to") and exists_strict(self.path.parent / e["file"])
        ]

    def _complete_pending_moves(self) -> list[int]:
        done: list[int] = []
        js = parse_journal(read_shared(self.journal_path))
        for e in js.closed:
            src = self.path.parent / e["file"]
            if e.get("archived_to") and exists_strict(src):
                if self._move_one(src, Path(e["archived_to"]), e["archived_sha256"]) == "done":
                    done.append(e["n"])
        return done
