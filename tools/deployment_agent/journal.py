"""Append-only JSONL journal for one rotation target. Ids and prefixes only.

One file per target, ``<dir>/rotation-<target>.jsonl``. Every entry is one line,
written with a single ``write`` and ``fsync`` before the engine moves on, so a
crash leaves at worst a torn final line, which the reader skips and counts.

What an entry may contain is a closed list (``ALLOWED_FIELDS``) and every string
in it passes ``looks_like_secret`` (plus a literal check against any secret the
engine registered with ``Journal.guard``). A violation raises
``JournalSecretError`` and writes nothing: the journal is the audit trail and must
be safe to paste into a ticket. Credential values live only in the stage/backup
files the rotator manages (mode 0600, deleted when a run ends), never here.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .secrets_guard import SHA40, SecretValue, looks_like_secret
from .states import State, TERMINAL, check_transition

#: the only keys an entry may carry besides the ones the journal adds (seq, ts, target)
ALLOWED_FIELDS = frozenset(
    {"event", "state", "run_id", "cred_old", "cred_new", "snapshot", "reason", "ttl_days", "sha", "ref"}
)
TARGET_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,62}\Z")
# a short opaque handle (credential id, run id, approval reference)
_SHORT = re.compile(r"\A[A-Za-z0-9_.:-]{1,23}\Z")


class JournalSecretError(ValueError):
    """An entry contained something that looks like a secret (or a registered secret)."""


class JournalError(RuntimeError):
    pass


def validate_target(target: str) -> str:
    if not isinstance(target, str) or not TARGET_RE.match(target):
        raise ValueError(f"target {target!r} must match {TARGET_RE.pattern}")
    return target


class SecretGuard:
    """Literal check: refuses any journal text that contains a registered secret or a long piece of one."""

    def __init__(self) -> None:
        self._secrets: list[str] = []

    def add(self, secret: SecretValue) -> None:
        self._secrets.append(secret.reveal())

    def hit(self, text: str) -> bool:
        for s in self._secrets:
            if s in text:
                return True
            for i in range(0, max(1, len(s) - 7)):  # any 8-character piece, as renew_token masks
                if len(s) >= 8 and s[i : i + 8] in text:
                    return True
        return False


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)


class Journal:
    def __init__(self, directory: str | os.PathLike[str], target: str, guard: SecretGuard | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.target = validate_target(target)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"rotation-{self.target}.jsonl"
        self.guard = guard or SecretGuard()
        self._clock = clock
        self.torn_lines = 0

    # ---- reading -----------------------------------------------------------------
    def entries(self) -> list[dict[str, Any]]:
        self.torn_lines = 0
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with open(self.path, "rb") as fh:
            for raw in fh.read().split(b"\n"):
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self.torn_lines += 1
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
                else:
                    self.torn_lines += 1
        return out

    def last_transition(self) -> dict[str, Any] | None:
        for e in reversed(self.entries()):
            if e.get("event") == "transition":
                return e
        return None

    def pending(self) -> dict[str, Any] | None:
        """The last transition entry while its run is unfinished, or halted and not yet human-cleared."""
        last: dict[str, Any] | None = None
        cleared = False
        for e in self.entries():
            if e.get("event") == "transition":
                last, cleared = e, False
            elif e.get("event") == "halt_cleared":
                cleared = True
        if last is None:
            return None
        state = State(last["state"])
        if state is State.HALTED:
            return None if cleared else last
        return None if state in TERMINAL else last

    def is_halted(self) -> bool:
        p = self.pending()
        return bool(p and p["state"] == State.HALTED.value)

    # ---- writing -----------------------------------------------------------------
    def _check(self, fields: dict[str, Any]) -> None:
        unknown = set(fields) - ALLOWED_FIELDS
        if unknown:
            raise JournalSecretError(f"journal field(s) not allowed: {sorted(unknown)}")
        for key, value in fields.items():
            if isinstance(value, SecretValue):
                raise JournalSecretError(f"journal field {key!r} is a SecretValue")
            if key == "ttl_days":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise JournalSecretError("ttl_days must be an int")
                continue
            for s in _strings(value):
                if key == "sha" and SHA40.match(s):
                    if self.guard.hit(s):  # skip the shape check only, never the literal-secret check
                        raise JournalSecretError("journal field 'sha' equals a registered secret; nothing written")
                    continue
                if key in ("cred_old", "cred_new", "run_id", "snapshot", "ref") and not _SHORT.match(s):
                    raise JournalSecretError(f"journal field {key!r} must be a short opaque id")
                if looks_like_secret(s) or self.guard.hit(s):
                    raise JournalSecretError(f"journal field {key!r} looks like a secret; nothing written")

    def append(self, **fields: Any) -> dict[str, Any]:
        self._check(fields)
        entries = self.entries()
        entry: dict[str, Any] = {"seq": len(entries) + self.torn_lines + 1, "ts": int(self._clock()),
                                 "target": self.target, **fields}
        if fields.get("event") == "transition":
            prev: State | None = None
            halted_open = False
            for e in entries:
                if e.get("event") == "transition":
                    prev = State(e["state"])
                    halted_open = prev is State.HALTED
                elif e.get("event") == "halt_cleared":
                    halted_open = False
            if halted_open:
                raise JournalError("journal is halted; a human must clear it (halt_cleared) first")
            if prev is not None and prev in TERMINAL:
                prev = None  # a finished run: a new one may start
            check_transition(prev, State(fields["state"]))
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        data = line.encode("utf-8") + b"\n"
        needs_nl = False
        if self.path.exists() and self.path.stat().st_size:
            with open(self.path, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                needs_nl = fh.read(1) != b"\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (b"\n" if needs_nl else b"") + data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return entry

    def transition(self, state: State, **fields: Any) -> dict[str, Any]:
        return self.append(event="transition", state=state.value, **fields)

    def note(self, reason: str, **fields: Any) -> dict[str, Any]:
        return self.append(event="note", reason=reason, **fields)
