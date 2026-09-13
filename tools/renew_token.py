#!/usr/bin/env python3
"""renew_token - renew one agent's FIELD delegation token before it expires.

Standard library only: it runs from cron on the GB10 with system python3 and
on Windows for the tests. Output is ASCII, one line per step, and token ids
appear only as 8-character prefixes.

    renew_token.py --agent ID --base URL
        (--env-file PATH --env-key KEY | --json-file PATH --json-key KEY)
        [--renew-within-days 7] [--ttl-days N] [--lock-file PATH]
        [--verify-cmd "..."] [--verify-timeout 120] [--state-dir DIR]
        [--secret-file PATH] [--renew-revoked] [--check]

WHAT A RENEWAL IS, in this order (the guards are pinned by tests in
tools/tests/test_renew_token.py; docs/runbooks/token-renewal.md section 6 says
which guards a full-module mutation run confirmed and which it did not):

1. Read ONLY the named key from the store. An env-file key is one `KEY=VALUE`
   line; a json-file key is one top-level member whose value is a JSON string.
   The store is handled as opaque bytes: no other line or member is decoded,
   printed or rewritten. The value must be a lowercase uuid (else exit 2).
2. Take non-blocking exclusive locks (flock(2) on POSIX, so they exclude a bash
   `flock -n` on the same file; msvcrt byte 0 on Windows): ALWAYS the store's
   own lock `.<store name>.renew-lock` beside the store, whatever the flags,
   then --lock-file when given. Both are held until the run ends. Either held
   => the one line `skipped: lock held (...)` and exit 3.
3. Reconcile a journal left by a run that died or gave up: a minted token
   that never reached the store is revoked, and then that mint's window is
   swept again with the journal's own snapshot, leaving that id out (the run
   that wrote the journal may have left its sweep unfinished); a journal token
   of another agent is refused after that sweep; when that id was never
   issued, the agent's tokens are swept instead. A token that did reach the
   store is taken back to verification; a renewal whose verification had
   passed only retries the old token's revoke. Nothing new happens until that
   is done. A journal whose new token is in its own pre-mint snapshot is
   refused as invalid.
4. GET the current token. A token of another agent is refused (exit 2).
5. Decide: due when expired or expiring within --renew-within-days. A REVOKED
   token is refused (exit 2) unless --renew-revoked: a revocation is a human
   decision and a scheduled job must not silently undo it. --check prints the
   decision and exits 0 having done only GETs: no lock, no journal, no write.
6. Mint with the SAME agent_id, granted_by and scope list (same order), for
   --ttl-days or the current token's own lifetime clamped to [1, 30] days. An
   intent journal is written before the POST and the new id right after it,
   so the id is on disk BEFORE the swap. A refused or failed mint changes no
   store and ledgers `token.renewal_failed`. The agent's tokens are listed
   before the POST (the current token is always counted in that snapshot).
   The only token of that snapshot a renewal ever revokes is the current one,
   in step 10: never as a "new" token, never as an orphan. A 201 whose id is
   missing, not a uuid, in the snapshot, or never issued (404 on every read
   AND absent from a fresh token list) is a lost answer: nothing is revoked by
   that id, the intent journal is kept and the agent's tokens are swept for the
   token the mint really created. The answer and a fresh GET of the new id must
   both show the same agent, grantor, scope list and the requested lifetime
   (within TTL_SLACK seconds), and an active token; a GET that shows another
   grant for that id, or answers 404 for an id the token list does carry,
   revokes that id where it can AND sweeps; the intent journal is kept once
   that id is confirmed revoked, the minted journal naming it otherwise. An
   ANSWER that differs (it may be another token's whole row, another agent's
   included) also sweeps, leaving that id out, BEFORE that id is revoked or
   refused: once that id is confirmed revoked the journal is cleared, or the
   intent kept when the sweep could not finish or revoked another token.
7. Swap the store value atomically (temp file in the same directory, fsync,
   os.replace, mode kept) and read it back: every other byte must be
   identical, or the original bytes are written back.
8. Run --verify-cmd (no shell; `{new_token}`, which the command must contain,
   and RENEW_NEW_TOKEN_ID carry the new id). Then read BOTH tokens again:
   - the new token revoked or expired => refused (exit 2): nothing restored,
     nothing revoked, journal kept. Someone revoked the token the store holds;
     putting the old token back would undo that.
   - the old token revoked by someone else => the new token is revoked too,
     exit 2. A revocation is not worked around by the renewal that raced it.
   - either token unreadable => exit 1, nothing touched, journal kept.
9. Verification failed (non-zero, timeout, unstartable): the store is restored
   byte for byte and the new token revoked, exit 1 - but only while the old
   token is still active. An old token that is expired, missing, or was
   already revoked before the renewal began (--renew-revoked) is never put
   back (the new token stays, unrevoked, journal kept), and a token the store
   still holds is never revoked (a restore that failed keeps the journal).
10. Verification passed: the store is read again and must still hold the new
   id (else exit 1, old token not revoked, journal kept). The journal records
   phase `verified`, the OLD token is revoked, `token.renewed` is ledgered,
   the journal is cleared, exit 0.

WHAT IT DOES NOT DO. It does not prove anything the verify command does not
prove: the old token is revoked only after --verify-cmd exits 0, so the verify
command is required for a renewal. What the tool itself adds after an exit 0
is narrow: the store still holds the new id, and neither token was revoked
while the verifier ran. It cannot mint where the estate refuses to
(retired or killed agent, a grantor removed from an armed DOA roster, a TTL
over the roster's max_ttl_days): that fails loudly and changes nothing. It does
not notify anyone: exit status and the log are the signal. A ledger append
that fails is reported and never changes the exit status of a renewal that
succeeded.

SECRETS. x-field-auth comes from FIELD_SHARED_SECRET or --secret-file, with
estate_probe's rules: a value with whitespace, control or non-ASCII characters
is refused before use, it is never printed (stdout and stderr are redacted,
including the verify command's relayed output), redirects are never followed,
and a cleartext non-loopback, non-private base is refused. The verify
command's output is relayed from its last 64 KiB starting at a complete line
(a line the window cuts is dropped whole, so neither the secret nor a token id
is ever printed in part), and in what is relayed every run of 8 or more
characters of the secret is masked, as is every run of 8 or more characters
of a full token id past its 8-character prefix, also when the verifier's own
output broke the value across lines (PowerShell wraps error records).

Exit status: 0 renewed / not due / --check, 1 failed (nothing half-done is
left without a journal), 2 refused (usage, store, agent, secret, revoked, a
revocation during a renewal), 3 lock held.
"""
from __future__ import annotations

import argparse
import errno
import glob
import hashlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

VERSION = "1.5"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_LOCKED = 0, 1, 2, 3
DAY = 86400
MAX_TTL_DAYS = 30
HTTP_TIMEOUT = 30.0
#: clock-skew allowance around an interrupted mint. An orphan must ALSO be absent
#: from the token list snapshotted before the mint and carry the exact grant.
SWEEP_SLACK = 120
VERIFY_OUTPUT_MAX = 64 * 1024
#: in relayed verifier output, a run of this many characters of the secret, or of a
#: full token id past its prefix, is masked wherever it appears (line breaks ignored)
FRAGMENT = 8
#: a token GET that answers 404 is read this many times before the 404 is believed:
#: the delegation authority's SQLite store can answer a spurious 404 under
#: concurrent reads (reproduced 2026-09-12), and a 404 decides between refusing,
#: and treating a token as gone.
NOT_FOUND_READS = 3
NOT_FOUND = f"NOT confirmed revoked: not found on {NOT_FOUND_READS} reads"
#: a minted token's expires_at - issued_at must be the ttl_seconds asked for, within this. The authority
#: computes expires_at = issued_at + ttl_seconds exactly and refuses (403) rather than clamps a TTL over
#: the roster's maximum, so any other lifetime is an altered request or answer.
TTL_SLACK = 5
#: what a confirmation GET can show for the id a mint answer named that is a GRANT other than the one asked
#: for (as opposed to a malformed read, another row, or an inactive token)
GRANT_FIELDS = ("agent_id", "granted_by", "scope", "lifetime")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
AGENT_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CLAUSE = re.compile(r"[A-Z]\.[a-z_]{1,40}")
#: minting: intent recorded, POST in flight. minted: the new id is on disk (the
#: store may or may not hold it yet). verified: the new token passed verification
#: in the store; only the old token's revoke and the ledger remain.
PHASES = ("minting", "minted", "verified")
_WS = re.compile(r"[ \t\n\r]*")


class Refused(Exception):
    """Exit 2: a human has to look. Anything half-done is named in the message
    and left with its journal."""


def say(line: str) -> None:
    print(line, flush=True)


def prefix(token_id: str | None) -> str:
    return (token_id or "")[:8] or "?"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- secrets and transport (estate_probe's rules) ----------------------------------


def read_secret(secret_file: str | None) -> str | None:
    if secret_file:
        try:
            with open(secret_file, encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            raise Refused("--secret-file is not readable")
        if not value:
            raise Refused("--secret-file is empty")
    else:
        value = os.environ.get("FIELD_SHARED_SECRET", "")
    if value and (not value.isascii() or not value.isprintable() or any(c.isspace() for c in value)):
        raise Refused("shared secret contains whitespace, control or non-ASCII characters (value not shown)")
    return value or None


def secret_forms(secret: str | None) -> tuple[str, ...]:
    """The secret as printed verbatim, and as repr() or a traceback prints it."""
    return (secret, repr(secret)[1:-1]) if secret else ()


def _occurrences(text: str, part: str):
    at = text.find(part)
    while at != -1:
        yield at
        at = text.find(part, at + 1)


def scrub(lines: list[str], secrets: tuple[str, ...], ids: tuple[str, ...]) -> list[str]:
    """Mask, in lines relayed from a verify command, every run of FRAGMENT or more
    characters of a secret form (as <redacted>) and of a full token id past its
    8-character prefix (as ...). The lines are searched joined, so a value the
    verifier's output broke across lines is masked on both sides of the break."""
    joined = "".join(lines)
    marks: list[str | None] = [None] * len(joined)
    shown = [False] * len(joined)  # an id's own prefix stays readable
    for token in ids:
        for at in _occurrences(joined, token[:FRAGMENT]):
            shown[at:at + FRAGMENT] = [True] * FRAGMENT
    for needle, mark, first in [(s, "<redacted>", 0) for s in secrets] + [(t, "...", 1) for t in ids]:
        size = min(FRAGMENT, len(needle))
        for i in range(first, len(needle) - size + 1):
            for at in _occurrences(joined, needle[i:i + size]):
                for k in range(at, at + size):
                    if mark == "<redacted>" or (not shown[k] and marks[k] is None):
                        marks[k] = mark
    out, pos = [], 0
    for line in lines:
        piece, run = [], None
        for k in range(pos, pos + len(line)):
            if marks[k] is None:
                piece.append(joined[k])
            elif marks[k] != run:
                piece.append(marks[k])
            run = marks[k]
        out.append("".join(piece))
        pos += len(line)
    return out


class Redact:
    """Nothing written to stdout/stderr (tracebacks and relayed verify output
    included) can carry the secret verbatim."""

    def __init__(self, stream, secret: str):
        self._s, self._needles = stream, set(secret_forms(secret))

    def write(self, text):
        for needle in self._needles:
            text = text.replace(needle, "<redacted>")
        return self._s.write(text)

    def __getattr__(self, name):
        return getattr(self._s, name)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer, never a hop: the header must not travel


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


class Api:
    def __init__(self, base: str, secret: str | None):
        self.base = base.rstrip("/")
        self._secret = secret

    def call(self, method: str, path: str, body: Any | None = None,
             timeout: float = HTTP_TIMEOUT) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if self._secret:
            headers["x-field-auth"] = self._secret
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                raw, status = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            status = exc.code
        except Exception as exc:  # the type name only: never a message
            return 0, {"transport_error": type(exc).__name__}
        try:
            return status, (json.loads(raw) if raw else None)
        except ValueError:
            return status, {"non_json_bytes": len(raw)}


def http_detail(status: int, body: Any) -> str:
    """What may be printed about a response: the status, a transport error's
    type name, and a clause id. Never a body (an upstream can reflect headers)."""
    if status == 0 and isinstance(body, dict):
        return f"transport error {body.get('transport_error', '?')}"
    detail = body.get("detail") if isinstance(body, dict) else None
    clause = detail.get("clause_id") if isinstance(detail, dict) else None
    if isinstance(clause, str) and CLAUSE.fullmatch(clause):
        return f"HTTP {status} {clause}"
    return f"HTTP {status}"


def clause_of(body: Any) -> str | None:
    detail = body.get("detail") if isinstance(body, dict) else None
    clause = detail.get("clause_id") if isinstance(detail, dict) else None
    return clause if isinstance(clause, str) and CLAUSE.fullmatch(clause) else None


# -- the store: one value, every other byte untouched ------------------------------


class Store:
    def __init__(self, kind: str, path: str, key: str):
        self.kind, self.path, self.key = kind, os.path.abspath(path), key

    def describe(self) -> str:
        return f"{self.kind} {self.path} key {self.key}"

    def read(self) -> bytes:
        if os.path.islink(self.path):
            raise Refused(f"store {self.path} is a symlink; os.replace would replace the link, not its target")
        if hasattr(os, "geteuid") and os.path.exists(self.path) and os.stat(self.path).st_uid != os.geteuid():
            raise Refused(f"store {self.path} is owned by uid {os.stat(self.path).st_uid}, not this user; "
                          "a replaced file would change owner. Run as the store's owner")
        try:
            with open(self.path, "rb") as fh:
                return fh.read()
        except OSError as exc:
            raise Refused(f"store {self.path} is not readable ({type(exc).__name__})")

    def locate(self, raw: bytes) -> tuple[int, int, str]:
        """(start, end, token) of the value's bytes. Refuses anything ambiguous."""
        return self._env(raw) if self.kind == "env-file" else self._json(raw)

    def encode(self, token: str) -> bytes:
        return token.encode() if self.kind == "env-file" else b'"' + token.encode() + b'"'

    def _env(self, raw: bytes) -> tuple[int, int, str]:
        exact = self.key.encode() + b"="
        loose = re.compile(rb"[ \t]*(?:export[ \t]+)?" + re.escape(self.key.encode()) + rb"[ \t]*=")
        hits, strict, offset = 0, [], 0
        for line in raw.split(b"\n"):
            if loose.match(line):  # only the key name is compared: no other value is read
                hits += 1
                if line.startswith(exact):
                    strict.append((offset + len(exact), offset + len(line)))
            offset += len(line) + 1
        if hits != 1 or len(strict) != 1:
            raise Refused(f"{self.key} must be defined exactly once as a plain {self.key}=VALUE line "
                          f"(found {hits} definition(s), {len(strict)} plain); nothing written")
        start, end = strict[0]
        return start, end, self._uuid(raw[start:end])

    def _json(self, raw: bytes) -> tuple[int, int, str]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise Refused("json-file is not UTF-8; nothing written")
        i = 1 if text.startswith("\ufeff") else 0
        try:
            json.loads(text[i:])
        except ValueError:
            raise Refused("json-file is not valid JSON; nothing written")
        decoder, found = json.JSONDecoder(), []
        i = _WS.match(text, i).end()
        if text[i:i + 1] != "{":
            raise Refused("json-file is not a JSON object; nothing written")
        i = _WS.match(text, i + 1).end()
        if text[i:i + 1] == "}":
            i += 1
        else:
            while True:
                name, i = json.decoder.scanstring(text, i + 1)
                i = _WS.match(text, i).end() + 1  # past ':'
                i = _WS.match(text, i).end()
                start = i
                value, i = decoder.raw_decode(text, i)
                if name == self.key:
                    found.append((start, i, value))
                i = _WS.match(text, i).end()
                if text[i] == "}":
                    break
                i = _WS.match(text, i + 1).end()  # past ','
        if len(found) != 1:
            raise Refused(f"top-level key {self.key!r} must appear exactly once (found {len(found)}); nothing written")
        start, end, value = found[0]
        if not isinstance(value, str) or text[start:end] != '"' + value + '"':
            raise Refused(f"{self.key!r} must be a plain JSON string holding a lowercase uuid; nothing written")
        token = self._uuid(value.encode("utf-8"))
        byte_start = len(text[:start].encode("utf-8"))
        return byte_start, byte_start + (end - start), token

    def _uuid(self, value: bytes) -> str:
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError:
            text = ""
        if not UUID.fullmatch(text):
            raise Refused(f"the value of {self.key} is not a lowercase uuid (value not shown); nothing written")
        return text


def write_atomic(path: str, data: bytes, mode: int | None) -> None:
    """Temp file in the same directory, fsync, keep mode, os.replace, fsync dir."""
    folder, name = os.path.split(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.renew-tmp-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if os.name != "nt":
        dfd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def replace_value(store: Store, expect: bytes, start: int, end: int, token: str) -> tuple[bool, str]:
    """Write `expect` with [start:end] replaced by `token`, then read it back.

    Every byte outside the value must be identical and the value must parse
    back as exactly `token`; otherwise `expect` is written back and checked.
    Returns (ok, message)."""
    data = expect[:start] + store.encode(token) + expect[end:]
    mode = os.stat(store.path).st_mode & 0o7777
    try:
        write_atomic(store.path, data, mode)
        with open(store.path, "rb") as fh:
            back = fh.read()
        new_end = start + len(store.encode(token))
        ok = (back[:start] == expect[:start] and back[new_end:] == expect[end:]
              and store.locate(back)[2] == token)
    except (OSError, Refused) as exc:
        ok, failure = False, type(exc).__name__
    else:
        failure = "read-back differs outside the value"
    if ok:
        return True, f"{len(expect) - (end - start)} other bytes identical; mode {oct(mode & 0o777)}"
    try:  # a failed os.replace never touched the file: do not report a false alarm
        with open(store.path, "rb") as fh:
            untouched = fh.read() == expect
    except OSError:
        untouched = False
    if untouched:
        return False, f"write failed ({failure}); the original bytes are still in place"
    try:
        write_atomic(store.path, expect, mode)
        with open(store.path, "rb") as fh:
            restored = fh.read() == expect
    except OSError:
        restored = False
    if restored:
        return False, f"write failed ({failure}); original bytes written back and confirmed"
    return False, f"write failed ({failure}); RESTORING THE ORIGINAL BYTES ALSO FAILED - check {store.path}"


# -- lock ---------------------------------------------------------------------------

_HELD = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, getattr(errno, "EDEADLK", -1)}


def acquire_lock(path: str) -> int | None:
    """A held fd, or None when another process holds the lock."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise Refused(f"lock file {path} cannot be opened ({type(exc).__name__})")
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in _HELD:
            return None
        raise
    return fd


def release_lock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


# -- journal --------------------------------------------------------------------------


class Journal:
    def __init__(self, state_dir: str, agent: str, store: Store):
        digest = sha256(f"{store.path}\0{store.key}\0{agent}".encode())[:12]
        self.path = os.path.join(os.path.abspath(state_dir), f"renew-{agent}-{digest}.json")
        self.agent, self.store = agent, store

    def load(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            raise Refused(f"journal {self.path} is unreadable; a human must reconcile it (nothing done)")
        problem = self._invalid(data)
        if problem:
            raise Refused(f"journal {self.path} is not a valid renewal journal ({problem}); nothing done")
        return data

    def _invalid(self, d: Any) -> str | None:
        if not isinstance(d, dict) or d.get("version") != 1:
            return "not a version-1 journal"
        if d.get("agent") != self.agent or d.get("store") != self.store.path or d.get("key") != self.store.key:
            return "it belongs to a different agent, store or key"
        if d.get("phase") not in PHASES:
            return "unknown phase"
        if not UUID.fullmatch(str(d.get("old_token"))):
            return "old_token is not a uuid"
        if d["phase"] != "minting" and not UUID.fullmatch(str(d.get("new_token"))):
            return "new_token is not a uuid"
        if not isinstance(d.get("old_revoked"), bool):
            return "old_revoked is not a boolean"
        if not isinstance(d.get("granted_by"), str) or not _scope_ok(d.get("scope")):
            return "grant is malformed"
        if parse_ts(d.get("started_at")) is None or not re.fullmatch(r"[0-9a-f]{64}", str(d.get("store_sha256_before"))):
            return "timestamps or digest malformed"
        known = d.get("known_tokens")
        if not isinstance(known, list) or not all(isinstance(t, str) for t in known):
            return "known_tokens malformed"
        if d["phase"] != "minting" and d["new_token"] in known:
            return "new_token existed before the mint (it is in known_tokens)"
        return None

    def write(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        write_atomic(self.path, json.dumps(data, indent=2, sort_keys=True).encode() + b"\n", 0o600)

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def _scope_ok(scope: Any) -> bool:
    return isinstance(scope, list) and bool(scope) and all(isinstance(s, str) and s for s in scope)


def token_problem(tok: Any) -> str | None:
    if not isinstance(tok, dict):
        return "not an object"
    if not UUID.fullmatch(str(tok.get("token_id"))):
        return "token_id"
    if not isinstance(tok.get("agent_id"), str) or not tok["agent_id"]:
        return "agent_id"
    if not isinstance(tok.get("granted_by"), str) or not tok["granted_by"]:
        return "granted_by"
    if not _scope_ok(tok.get("scope")):
        return "scope"
    if parse_ts(tok.get("issued_at")) is None or parse_ts(tok.get("expires_at")) is None:
        return "issued_at/expires_at"
    if not isinstance(tok.get("revoked"), bool):
        return "revoked"
    return None


# -- the renewal -------------------------------------------------------------------------


class Renewal:
    secret: str | None = None  # masked in relayed verify output (see scrub)

    def __init__(self, args: argparse.Namespace, secret: str | None):
        self.a, self.secret = args, secret
        self.api = Api(args.base, secret)
        if args.env_file:
            self.store = Store("env-file", args.env_file, args.env_key)
        else:
            self.store = Store("json-file", args.json_file, args.json_key)
        state_dir = args.state_dir or os.path.join(os.path.dirname(self.store.path), ".renew-token")
        self.journal = Journal(state_dir, args.agent, self.store)
        # The STORE's own lock, beside it, is taken by every renewal of that store whatever
        # its flags (--lock-file, --state-dir): a hand run without --lock-file must never
        # treat a live scheduled run's journal as a crash. --lock-file is taken as well.
        folder, name = os.path.split(self.store.path)
        self.lock_paths = [os.path.join(folder, f".{name}.renew-lock")]
        if args.lock_file and os.path.normcase(os.path.abspath(args.lock_file)) != os.path.normcase(self.lock_paths[0]):
            self.lock_paths.append(os.path.abspath(args.lock_file))
        self.verify_argv = split_command(args.verify_cmd) if args.verify_cmd else []

    # step 1 - 2 ------------------------------------------------------------------------
    def run(self) -> int:
        a = self.a
        say(f"renew_token {VERSION} {iso(utcnow())} agent={a.agent} base={self.api.base} "
            f"store={self.store.describe()}{' (check only)' if a.check else ''}")
        raw = self.store.read()
        current = self.store.locate(raw)[2]
        say(f"store: {self.store.key} holds token {prefix(current)}")
        if a.check:
            return self.check(current)
        held: list[int] = []
        try:
            for path in self.lock_paths:  # fixed order, never blocking
                fd = acquire_lock(path)
                if fd is None:
                    say(f"skipped: lock held ({path})")
                    return EXIT_LOCKED
                held.append(fd)
            say(f"lock: acquired {' and '.join(self.lock_paths)}")
            return self.locked()
        finally:
            for fd in reversed(held):
                release_lock(fd)

    def locked(self) -> int:
        self.sweep_stale_temp()
        rc = self.recover()
        if rc is not None:
            return rc
        raw = self.store.read()
        start, end, current = self.store.locate(raw)
        tok = self.current_token(current)
        if isinstance(tok, int):
            return tok
        due, why, left = self.decide(tok)
        if tok["revoked"] and not self.a.renew_revoked:
            raise Refused(f"token {prefix(current)} is REVOKED. A revocation is a human decision and this "
                          "tool does not undo it; re-run with --renew-revoked to renew it deliberately. "
                          "Nothing written")
        if not due:
            say(f"not due: {int(left)} days left (expires {iso(parse_ts(tok['expires_at']))}; "
                f"renewal window {self.a.renew_within_days} days)")
            return EXIT_OK
        say(f"decide: due ({why})")
        return self.renew(raw, start, end, tok)

    def check(self, current: str) -> int:
        try:
            pending = self.journal.load()
        except Refused as exc:
            pending = None
            say(f"check: {exc}")
        if pending:
            say(f"check: journal present (phase {pending['phase']}); the next real run reconciles it first")
        tok = self.current_token(current)
        if isinstance(tok, int):
            return tok
        due, why, left = self.decide(tok)
        if tok["revoked"] and not self.a.renew_revoked:
            say("check: token is REVOKED; a real run refuses (exit 2) without --renew-revoked")
        elif due:
            say(f"check: due ({why}); a real run would mint {self.ttl(tok, quiet=True) / DAY:g} days with the same "
                f"grantor and {len(tok['scope'])} scope entries")
        else:
            say(f"check: not due: {int(left)} days left")
        return EXIT_OK

    def sweep_stale_temp(self) -> None:
        folder, name = os.path.split(self.store.path)
        stale = glob.glob(os.path.join(glob.escape(folder), glob.escape(f".{name}.renew-tmp-") + "*"))
        for path in stale:
            os.unlink(path)
        if stale:
            say(f"store: removed {len(stale)} stale temp file(s) left by an interrupted swap")

    # step 3 -------------------------------------------------------------------------------
    def recover(self) -> int | None:
        j = self.journal.load()
        if j is None:
            say("journal: none")
            return None
        current = self.store.locate(self.store.read())[2]
        old = j["old_token"]
        if j["phase"] == "minting":
            say(f"recovery: a run was interrupted during its mint (started {j['started_at']}); sweeping for an orphan")
            ok, revoked = self.sweep_orphans(j, current)
            if not ok:
                say("recovery: sweep incomplete; journal kept")
                return EXIT_FAILED
            if revoked:
                self.ledger("token.renewal_failed", {"reason": "interrupted_during_mint", "http_status": None,
                                                     "orphans_revoked": revoked, "old_prefix": prefix(old)})
            self.journal.clear()
            say("journal: cleared")
            return None
        new = j["new_token"]
        if j["phase"] == "verified":
            if current != new:
                raise Refused(f"journal {self.journal.path} records that {prefix(new)} passed verification, but "
                              f"{self.store.key} now holds {prefix(current)}: the store was changed after that. "
                              f"Nothing done; old token {prefix(old)} may already be revoked. A human reconciles "
                              "the journal (runbook 4.2)")
            say(f"recovery: {prefix(new)} had passed verification in the store; retrying only the old token's "
                "revoke and the ledger (no verification, no rollback)")
            checked = self.check_tokens(j)
            if isinstance(checked, int):
                return checked
            return self.close(j, checked)
        if current != new:
            say(f"recovery: token {prefix(new)} was minted but never reached the store; revoking it")
            # The run that left this journal may have abandoned an untrusted mint answer with its sweep unfinished
            # (the token list could not be read, then this id's revoke failed or was refused), and the journal does
            # not say so. Once this id is revoked, or refused as another agent's token, that mint's window is swept
            # again: with the journal's own snapshot and started_at (a late recovery sweeps THAT mint's window), and
            # this id left out.
            owed = dict(j, known_tokens=sorted(set(j["known_tokens"]) | {new}))
            try:
                ok, msg = self.revoke(new)
            except Refused:
                say(f"recovery: {prefix(new)} is not a token of {self.a.agent}; sweeping for the token that mint "
                    "created before refusing")
                self.sweep_orphans(owed, current)
                raise
            say(f"recovery: {prefix(new)} {msg}")
            reason, orphans = "interrupted_before_swap", 0
            if not ok and msg == NOT_FOUND and self.never_issued(new):
                # A mint answer named an id the authority never issued: revoking it can never succeed, and
                # the token that mint really created, if any, is an orphan only a sweep can find.
                say(f"recovery: {prefix(new)} is not in the agent's token list either: the id the mint answer "
                    "named was never issued; sweeping for the token that mint created")
                ok, orphans = self.sweep_orphans(j, current)
                reason = "mint_answer_never_issued"
            elif ok:
                say("recovery: sweeping for another token that mint created (its run may not have finished a sweep)")
                ok, orphans = self.sweep_orphans(owed, current)
            if not ok:
                say("recovery: journal kept")
                return EXIT_FAILED
            payload = {"reason": reason, "http_status": None, "old_prefix": prefix(old), "new_prefix": prefix(new)}
            if orphans:
                payload["orphans_revoked"] = orphans
            self.ledger("token.renewal_failed", payload)
            self.journal.clear()
            say("journal: cleared")
            return None
        say(f"recovery: the store already holds {prefix(new)} but the renewal did not finish; checking both tokens "
            "before verifying it again")
        checked = self.check_tokens(j)
        if isinstance(checked, int):
            return checked
        return self.verify_and_finish(None, j["store_sha256_before"], j)

    def sweep_orphans(self, j: dict, current: str) -> tuple[bool, int]:
        """Revoke tokens a lost mint response may have created: not in the list
        snapshotted before the mint, exact agent, grantor and scope, issued
        around the intent, and not the store's token."""
        status, tokens = self.api.call("GET", "/delegation/tokens?" + urllib.parse.urlencode({"agent_id": self.a.agent}))
        if status != 200 or not isinstance(tokens, list):
            say(f"sweep: could not list tokens ({http_detail(status, tokens)})")
            return False, 0
        started = parse_ts(j["started_at"])
        low, high = started - timedelta(seconds=SWEEP_SLACK), started + timedelta(seconds=HTTP_TIMEOUT + SWEEP_SLACK)
        ok, revoked = True, 0
        for t in tokens:
            if token_problem(t) or t["revoked"] or t["agent_id"] != self.a.agent:
                continue
            if t["granted_by"] != j["granted_by"] or t["scope"] != j["scope"]:
                continue
            if t["token_id"] in (current, j["old_token"]) or t["token_id"] in j["known_tokens"]:
                continue
            if not low <= parse_ts(t["issued_at"]) <= high:
                continue
            done, msg = self.revoke(t["token_id"])
            say(f"sweep: orphan {prefix(t['token_id'])} {msg}")
            ok, revoked = ok and done, revoked + (1 if done else 0)
        if ok and not revoked:
            say("sweep: no orphan token found")
        return ok, revoked

    def never_issued(self, token_id: str) -> bool:
        """After a 404 on every read of `token_id`: True only when the agent's token list answers now and
        does not carry it either, so two different reads agree the authority never issued that id. A list
        that cannot be read is never taken as that proof."""
        status, tokens = self.api.call("GET", "/delegation/tokens?" + urllib.parse.urlencode({"agent_id": self.a.agent}))
        if status != 200 or not isinstance(tokens, list):
            say(f"confirm: the agent's tokens could not be listed ({http_detail(status, tokens)}); "
                f"{prefix(token_id)} is not taken as never issued")
            return False
        return token_id not in {t.get("token_id") for t in tokens if isinstance(t, dict)}

    # step 4 - 5 -----------------------------------------------------------------------------
    def current_token(self, current: str) -> dict | int:
        status, tok = self.get_token(current)
        if status == 404:
            raise Refused(f"token {prefix(current)} is not known to the delegation authority, so its grantor "
                          "and scope cannot be carried forward; nothing written")
        if status != 200:
            hint = " (x-field-auth missing or wrong)" if status == 401 else ""
            say(f"token: GET {prefix(current)} failed ({http_detail(status, tok)}){hint}; nothing written")
            return EXIT_FAILED
        problem = token_problem(tok)
        if problem or tok["token_id"] != current:
            say(f"token: malformed response for {prefix(current)} ({problem or 'token_id'}); nothing written")
            return EXIT_FAILED
        if tok["agent_id"] != self.a.agent:
            raise Refused(f"token {prefix(current)} belongs to agent {ascii(tok['agent_id'])}, not "
                          f"{ascii(self.a.agent)}; nothing written")
        say(f"token: {prefix(current)} agent={self.a.agent} granted_by={ascii(tok['granted_by'])} "
            f"scope={len(tok['scope'])} entries expires {iso(parse_ts(tok['expires_at']))}"
            f"{' REVOKED' if tok['revoked'] else ''}")
        return tok

    def decide(self, tok: dict) -> tuple[bool, str, float]:
        left = (parse_ts(tok["expires_at"]) - utcnow()).total_seconds() / DAY
        if tok["revoked"]:
            return True, "revoked", left
        if left <= 0:
            return True, f"expired {-left:.1f} days ago", left
        if left <= self.a.renew_within_days:
            return True, f"expires within {self.a.renew_within_days} days: {left:.1f} days left", left
        return False, "", left

    def ttl(self, tok: dict, quiet: bool = False) -> int:
        if self.a.ttl_days:
            seconds = self.a.ttl_days * DAY
            note = "--ttl-days"
        else:
            life = int((parse_ts(tok["expires_at"]) - parse_ts(tok["issued_at"])).total_seconds())
            seconds = min(max(life, DAY), MAX_TTL_DAYS * DAY)
            note = f"current lifetime {life / DAY:.2f} days" + (", clamped to [1, 30] days" if seconds != life else "")
        if not quiet:
            say(f"ttl: {seconds} s = {seconds / DAY:g} days ({note})")
            if seconds <= self.a.renew_within_days * DAY:
                say(f"note: that lifetime is inside the {self.a.renew_within_days}-day renewal window, "
                    "so the next run renews again")
        return seconds

    # step 6 - 7 ---------------------------------------------------------------------------
    def renew(self, raw: bytes, start: int, end: int, tok: dict) -> int:
        agent, old, grantor, scope = self.a.agent, tok["token_id"], tok["granted_by"], list(tok["scope"])
        ttl = self.ttl(tok)
        # Snapshot the agent's tokens first: only a token that did not exist before
        # this mint can ever be swept as its orphan.
        status, listed = self.api.call("GET", "/delegation/tokens?" + urllib.parse.urlencode({"agent_id": agent}))
        if status != 200 or not isinstance(listed, list):
            say(f"mint: not attempted; the agent's tokens could not be listed first ({http_detail(status, listed)})")
            return EXIT_FAILED
        # The current token is in the snapshot even if the list answer missed it (the store race).
        known = sorted({t["token_id"] for t in listed if isinstance(t, dict) and isinstance(t.get("token_id"), str)}
                       | {old})
        intent = {"version": 1, "phase": "minting", "agent": agent, "store": self.store.path,
                  "key": self.store.key, "old_token": old, "old_revoked": tok["revoked"], "granted_by": grantor,
                  "scope": scope, "ttl_seconds": ttl, "known_tokens": known, "started_at": utcnow().isoformat(),
                  "store_sha256_before": sha256(raw)}
        try:
            self.journal.write(intent)
        except OSError as exc:
            say(f"journal: cannot write {self.journal.path} ({type(exc).__name__}); not minting")
            return EXIT_FAILED
        say(f"journal: intent recorded ({self.journal.path})")
        status, body = self.api.call("POST", "/delegation/tokens",
                                     {"agent_id": agent, "granted_by": grantor, "scope": scope, "ttl_seconds": ttl})
        new = body.get("token_id") if isinstance(body, dict) else None
        # An answer that names no NEW token (an id that is missing, not a uuid, or one of the agent's tokens
        # from before this mint, the current token's own id included) is a lost answer: nothing may ever be
        # revoked by the id it names, and the mint may have happened.
        if status != 201 or not UUID.fullmatch(str(new)) or new in known:
            return self.mint_failed(status, body, intent, current=old)
        minted = dict(intent, phase="minted", new_token=new)
        try:
            self.journal.write(minted)
        except OSError as exc:
            return self.abandon(new, old, "journal_failed", f"cannot record the new token ({type(exc).__name__})")
        say(f"mint: HTTP 201 new token {prefix(new)}; journal records it before the swap")
        problem = self.same_grant(body, new, grantor, scope, ttl)
        if problem:
            # The ANSWER itself shows another grant, lifetime or row. It may be another token's row put in place
            # of this mint's (a hop that replaced the whole answer body): the snapshot rule and the confirmation
            # cannot see that, so the agent's tokens are swept for the token this mint really created.
            return self.abandon(new, old, "mint_mismatch", f"mint response differs from the current grant ({problem})",
                                sweep=intent, answer=True)
        status, confirmed = self.get_token(new)
        problem = self.same_grant(confirmed, new, grantor, scope, ttl) if status == 200 else http_detail(status, confirmed)
        if problem:
            if status == 404 and self.never_issued(new):
                say(f"confirm: {prefix(new)} was never issued (not found on {NOT_FOUND_READS} reads, and not in the "
                    "agent's token list): the mint answer named an id that does not exist")
                try:
                    self.journal.write(intent)  # nothing to revoke by that id: back to the intent, swept below
                except OSError as exc:
                    say(f"journal: cannot return to the intent ({type(exc).__name__})")
                    return self.abandon(new, old, "mint_unconfirmed", "new token was never issued", sweep=intent)
                return self.mint_failed(201, body, intent, current=old)
            if status == 404 or (status == 200 and problem in GRANT_FIELDS):
                # The authority cannot find that id (while its token list has it), or its own row is not the grant
                # the answer described: the id may not be the token this mint created, so the agent's tokens are
                # swept as well.
                return self.abandon(new, old, "mint_unconfirmed", f"new token could not be confirmed ({problem})",
                                    sweep=intent)
            return self.abandon(new, old, "mint_unconfirmed", f"new token could not be confirmed ({problem})")
        say(f"confirm: {prefix(new)} persisted with the same agent, grantor and {len(scope)} scope entries in "
            f"the same order and the requested {ttl} s lifetime, expires {iso(parse_ts(confirmed['expires_at']))}")
        if self.store.read() != raw:
            return self.abandon(new, old, "store_changed", "the store changed after it was read; not swapping")
        ok, msg = replace_value(self.store, raw, start, end, new)
        if not ok:
            say(f"swap: {msg}")
            return self.abandon(new, old, "swap_failed", "store swap failed")
        say(f"swap: {self.store.key} {prefix(old)} -> {prefix(new)} (atomic replace; {msg})")
        return self.verify_and_finish(raw, sha256(raw), minted)

    def same_grant(self, tok: Any, new: str, grantor: str, scope: list[str], ttl: int) -> str | None:
        problem = token_problem(tok)
        if problem:
            return f"malformed {problem}"
        if tok["token_id"] != new:
            return "token_id"
        if tok["agent_id"] != self.a.agent:
            return "agent_id"
        if tok["granted_by"] != grantor:
            return "granted_by"
        if tok["scope"] != scope:
            return "scope"
        if abs((parse_ts(tok["expires_at"]) - parse_ts(tok["issued_at"])).total_seconds() - ttl) > TTL_SLACK:
            return "lifetime"
        if tok["revoked"] or parse_ts(tok["expires_at"]) <= utcnow():
            return "not active"
        return None

    def mint_failed(self, status: int, body: Any, intent: dict, current: str) -> int:
        if status == 201:
            say("mint: FAILED (HTTP 201 without a new token id: missing, not a uuid, a token that existed before "
                "the mint (the current token's own id among them), or an id never issued); nothing swapped and "
                "nothing revoked by that id")
        else:
            say(f"mint: FAILED ({http_detail(status, body)}); nothing swapped")
        # A 5xx or a lost response may follow a token the authority DID persist.
        maybe_minted = status == 0 or status >= 500 or status == 201
        if maybe_minted:
            self.sweep_orphans(intent, current)
        reason = "mint_transport_error" if status == 0 else ("mint_response_invalid" if status == 201 else "mint_refused")
        self.ledger("token.renewal_failed", {"reason": reason, "http_status": status or None,
                                             "clause_id": clause_of(body), "old_prefix": prefix(current)})
        if maybe_minted:
            say("journal: intent kept, so the next run sweeps again for a token persisted late")
        else:
            self.journal.clear()
            say("journal: cleared")
        say(f"result: FAILED at mint; store and old token {prefix(current)} untouched")
        return EXIT_FAILED

    def abandon(self, new: str, old: str, reason: str, why: str, sweep: dict | None = None,
                answer: bool = False) -> int:
        """Undo a minted token this run will not swap in. With `sweep` (the intent journal), the id is not
        trusted to be the token the mint created: the agent's tokens are swept first, and the intent is
        kept so the next run sweeps again. With `answer` as well (the mint answer itself showed another
        grant, lifetime or row), the sweep leaves the named id to the revoke below, and the journal is
        cleared as for a plain abandon unless the sweep could not finish or revoked another token (so the
        answer did not name this mint's token): then the intent is kept."""
        say(f"abandon: {why}")
        keep_intent = sweep is not None
        if sweep is not None:
            swept, found = self.sweep_orphans(
                dict(sweep, known_tokens=sorted(set(sweep["known_tokens"]) | {new})) if answer else sweep, old)
            keep_intent = not answer or not swept or found > 0
        ok, msg = self.revoke_unless_stored(new)
        say(f"revoke-new: {prefix(new)} {msg}")
        self.ledger("token.renewal_failed", {"reason": reason, "http_status": None,
                                             "old_prefix": prefix(old), "new_prefix": prefix(new)})
        if not ok:
            say("journal: kept for the next run")
        elif not keep_intent:
            self.journal.clear()
            say("journal: cleared")
        else:
            try:
                self.journal.write(sweep)
                say("journal: intent kept, so the next run sweeps again")
            except OSError as exc:  # the minted journal stays: its (revoked) token is reconciled next run
                say(f"journal: cannot return to the intent ({type(exc).__name__}); kept for the next run")
        say(f"result: FAILED ({reason}); {self.store_summary(old, new)}; old token {prefix(old)} not revoked")
        return EXIT_FAILED

    # step 8 - 10 --------------------------------------------------------------------------
    def verify_and_finish(self, raw: bytes | None, before: str, j: dict) -> int:
        rc, detail = self.run_verify(j["new_token"], j["old_token"])
        checked = self.check_tokens(j)  # the verifier ran for a while: re-read both tokens first
        if isinstance(checked, int):
            return checked
        if rc == 0:
            return self.finish(j, checked)
        return self.undo(raw, before, j, rc, detail, checked)

    def token_state(self, token_id: str) -> tuple[str, str, dict | None]:
        """(active|revoked|expired|missing|unreadable, printable note, the token when read)."""
        status, tok = self.get_token(token_id)
        if status == 404:
            return "missing", f"not found on {NOT_FOUND_READS} reads", None
        if status != 200 or token_problem(tok):
            return "unreadable", f"GET failed ({http_detail(status, tok) if status != 200 else 'malformed'})", None
        if tok["token_id"] != token_id:
            return "unreadable", "the authority answered with a different token", None
        if tok["revoked"]:
            return "revoked", "REVOKED", tok
        if parse_ts(tok["expires_at"]) <= utcnow():
            return "expired", f"EXPIRED at {iso(parse_ts(tok['expires_at']))}", tok
        return "active", f"active until {iso(parse_ts(tok['expires_at']))}", tok

    def check_tokens(self, j: dict) -> dict | int:
        """Read both tokens of a renewal that has a new id in the store. A revocation
        someone else made while the renewal was in flight is never undone or worked around."""
        old, new, verified = j["old_token"], j["new_token"], j["phase"] == "verified"
        new_state, new_note, new_tok = self.token_state(new)
        old_state, old_note, _ = self.token_state(old)
        say(f"tokens: new {prefix(new)} {new_note}; old {prefix(old)} {old_note}")
        if new_tok is not None and new_tok["agent_id"] != self.a.agent:
            raise Refused(f"journal token {prefix(new)} belongs to another agent; not touching it (journal kept)")
        if new_state in ("revoked", "expired"):
            raise Refused(f"token {prefix(new)}, the renewal's new token, is {new_note} while the renewal was not "
                          f"finished; {self.store_summary(old, new)}. Nothing restored and nothing revoked: putting "
                          f"the old token back would undo that. Old token {prefix(old)} is {old_note}. Journal kept "
                          f"({self.journal.path}); a human decides (runbook 4.2)")
        if old_state == "revoked" and not j["old_revoked"] and not verified:
            return self.revoked_during_renewal(old, new)
        if new_state != "active" or old_state == "unreadable":
            say("tokens: cannot decide safely without both tokens' state; nothing restored or revoked. Journal kept: "
                "the next run reads them again")
            return EXIT_FAILED
        return {"new_tok": new_tok, "old_state": old_state, "old_note": old_note}

    def revoked_during_renewal(self, old: str, new: str) -> int:
        say(f"abandon: old token {prefix(old)} was REVOKED by someone else while this renewal was in flight. A "
            "revocation is not worked around, so the new token is revoked too")
        ok, msg = self.revoke(new)
        say(f"revoke-new: {prefix(new)} {msg}")
        self.ledger("token.renewal_failed", {"reason": "revoked_during_renewal", "http_status": None,
                                             "old_prefix": prefix(old), "new_prefix": prefix(new)})
        if ok:
            self.journal.clear()
            say("journal: cleared")
        else:
            say("journal: kept for the next run")
        raise Refused(f"token {prefix(old)} was revoked during the renewal; {self.store_summary(old, new)}, and "
                      f"{prefix(new)} is {'revoked' if ok else 'NOT confirmed revoked'}. {self.a.agent} stays halted "
                      "until a human decides (--renew-revoked renews deliberately)")

    def finish(self, j: dict, checked: dict) -> int:
        old, new = j["old_token"], j["new_token"]
        if self.stored_value() != new:
            say(f"store: {self.store.key} no longer holds {prefix(new)} after verification: the store was changed "
                "while the verifier ran, so the proof does not cover what the agent will use. Old token NOT revoked")
            self.ledger("token.renewal_failed", {"reason": "store_changed_during_verify", "http_status": None,
                                                 "old_prefix": prefix(old), "new_prefix": prefix(new)})
            say("journal: kept; the next run revokes the new token if the store still does not hold it")
            say(f"result: FAILED after verification; {self.store_summary(old, new)}")
            return EXIT_FAILED
        try:
            self.journal.write(dict(j, phase="verified"))
        except OSError as exc:
            say(f"journal: cannot record the verification ({type(exc).__name__}); old token NOT revoked. Journal "
                "kept: the next run verifies again")
            return EXIT_FAILED
        say("journal: verified; revoking the old token")
        return self.close(j, checked)

    def close(self, j: dict, checked: dict) -> int:
        old, new, new_tok = j["old_token"], j["new_token"], checked["new_tok"]
        ok, msg = self.revoke(old)
        if not ok:
            say(f"revoke-old: {prefix(old)} {msg}; it stays active until it expires. Journal kept (phase verified): "
                "the next run retries only the revoke")
            return EXIT_FAILED
        say(f"revoke-old: {prefix(old)} {msg}")
        self.ledger("token.renewed", {"old_prefix": prefix(old), "new_prefix": prefix(new),
                                      "expires_at": new_tok["expires_at"], "granted_by": new_tok["granted_by"],
                                      "scope_count": len(new_tok["scope"])})
        self.journal.clear()
        say("journal: cleared")
        say(f"result: renewed {prefix(old)} -> {prefix(new)}, expires {iso(parse_ts(new_tok['expires_at']))}")
        return EXIT_OK

    def undo(self, raw: bytes | None, before: str, j: dict, rc: int | None, detail: str, checked: dict) -> int:
        old, new = j["old_token"], j["new_token"]
        payload = {"reason": "verify_failed", "verify_rc": rc, "timed_out": detail == "timeout",
                   "old_prefix": prefix(old), "new_prefix": prefix(new)}
        if checked["old_state"] != "active":
            say(f"restore: NOT done: old token {prefix(old)} is {checked['old_note']}, so putting it back would "
                f"leave {self.a.agent} without a working token. The new token is not revoked either")
            self.ledger("token.renewal_failed", dict(payload, old_token_live=False))
            say("journal: kept; the next run verifies again")
            say(f"result: FAILED at verification ({detail}); {self.store_summary(old, new)}")
            return EXIT_FAILED
        restored = self.restore(raw, before, old, new)
        ok, msg = self.revoke_unless_stored(new)
        say(f"revoke-new: {prefix(new)} {msg}")
        self.ledger("token.renewal_failed", dict(payload, restore_failed=not restored))
        if restored and ok:
            self.journal.clear()
            say("journal: cleared")
        else:
            say("journal: kept for the next run")
        say(f"result: FAILED at verification ({detail}); {self.store_summary(old, new)}")
        return EXIT_FAILED

    def restore(self, raw: bytes | None, before: str, old: str, new: str) -> bool:
        """True when the store holds the old token afterwards."""
        current = self.store.read()
        start, end, value = self.store.locate(current)
        if value != new:
            say(f"restore: the store no longer holds {prefix(new)}; not touching it")
            return value == old
        ok, msg = replace_value(self.store, current, start, end, old)
        back = self.store.read()
        exact = back == raw if raw is not None else sha256(back) == before
        say(f"restore: {'store holds ' + prefix(old) + ' again' if ok else 'FAILED'} ({msg}); "
            f"byte-for-byte identical to before the renewal: {exact}")
        return ok

    def stored_value(self) -> str | None:
        """The token the store holds now, or None when it cannot be read or parsed."""
        try:
            return self.store.locate(self.store.read())[2]
        except Refused:
            return None

    def store_summary(self, old: str, new: str) -> str:
        held = self.stored_value()
        if held is None:
            return f"{self.store.key} CANNOT BE READ: check {self.store.path}"
        if held == old:
            return f"store holds {prefix(old)} (the old token)"
        if held == new:
            return f"store STILL HOLDS {prefix(new)} (the new token)"
        return f"store holds {prefix(held)} (neither the old nor the new token)"

    def run_verify(self, new: str, old: str) -> tuple[int | None, str]:
        argv = [part.replace("{new_token}", new) for part in self.verify_argv]
        env = dict(os.environ, RENEW_NEW_TOKEN_ID=new)
        timeout = self.a.verify_timeout
        say(f"verify: running {os.path.basename(argv[0])} (timeout {timeout:g} s)")
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        with tempfile.TemporaryFile() as out:  # a file, not a pipe: a killed tree cannot hang us
            try:
                proc = subprocess.Popen(argv, stdout=out, **kwargs)
            except OSError as exc:
                say(f"verify: could not start ({type(exc).__name__})")
                return None, "could not start"
            try:
                rc: int | None = proc.wait(timeout=timeout)
                detail = f"rc={rc}"
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                rc, detail = None, "timeout"
            size = out.seek(0, os.SEEK_END)
            self.relay(tail_lines(out, size), new, old, truncated=size > VERIFY_OUTPUT_MAX)
        say(f"verify: {'TIMED OUT after %g s; process tree killed' % timeout if rc is None else detail}")
        return rc, detail

    def relay(self, data: bytes, new: str, old: str, truncated: bool) -> None:
        text = data.decode("utf-8", "replace")
        for full in (new, old):
            text = text.replace(full, full[:8] + "...")
        lines = [line.encode("ascii", "backslashreplace").decode("ascii")  # scrub exactly what is printed
                 for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        lines = scrub(lines, secret_forms(self.secret), (new, old))
        while lines and not lines[-1].strip():
            lines.pop()
        if truncated:
            say("  verify| [earlier output truncated]")
            if not data:
                say(f"  verify| [its last {VERIFY_OUTPUT_MAX // 1024} KiB hold no complete line; not shown]")
        for line in lines:
            say("  verify| " + line)

    # plumbing -------------------------------------------------------------------------------
    def revoke_unless_stored(self, token_id: str) -> tuple[bool, str]:
        """Undo a token this run is abandoning, except the token the store holds (or
        may hold: a store that cannot be read). Revoking that would halt the agent on
        a token nobody decided to revoke; the journal is kept instead."""
        held = self.stored_value()
        if held is None:
            return False, "NOT revoked: the store cannot be read, so it may hold this token"
        if held == token_id:
            return False, "NOT revoked: the store holds it"
        return self.revoke(token_id)

    def revoke(self, token_id: str) -> tuple[bool, str]:
        """Revoke only a token confirmed to belong to --agent. Success means the
        authority answered revoked=true: a token it cannot find is NOT counted as
        revoked, so the journal that names it is kept."""
        status, tok = self.get_token(token_id)
        if status == 404:
            return False, f"NOT confirmed revoked: not found on {NOT_FOUND_READS} reads"
        if status != 200 or not isinstance(tok, dict):
            return False, f"revoke not attempted: GET failed ({http_detail(status, tok)})"
        if tok.get("token_id") != token_id:
            return False, "NOT confirmed revoked: the authority answered with a different token"
        if tok.get("agent_id") != self.a.agent:
            raise Refused(f"token {prefix(token_id)} does not belong to {self.a.agent}; refusing to revoke it")
        if tok.get("revoked") is True:
            return True, "was already revoked"
        status, body = self.api.call("POST", f"/delegation/tokens/{token_id}/revoke")
        if status == 200 and isinstance(body, dict) and body.get("revoked") is True \
                and body.get("token_id") == token_id:
            return True, "revoked"
        return False, f"revoke FAILED ({http_detail(status, body)})"

    def get_token(self, token_id: str) -> tuple[int, Any]:
        for attempt in range(NOT_FOUND_READS):
            status, tok = self.api.call("GET", f"/delegation/tokens/{token_id}")
            if status != 404:
                break
            if attempt + 1 < NOT_FOUND_READS:
                time.sleep(1)
        return status, tok

    def ledger(self, event_type: str, payload: dict) -> None:
        status, body = self.api.call("POST", "/ledger/events",
                                     {"event_type": event_type, "payload": payload, "agent_id": self.a.agent})
        if status in (200, 201):
            say(f"ledger: {event_type} appended")
        else:
            say(f"ledger: {event_type} append FAILED ({http_detail(status, body)}); reported here only, "
                "exit status unchanged")


def tail_lines(fh, size: int) -> bytes:
    """The verify command's output, or its last VERIFY_OUTPUT_MAX bytes from the
    first line that starts inside them. A line the window cuts is dropped whole:
    the secret or a token id (neither can hold a line break) may straddle the cut."""
    if size <= VERIFY_OUTPUT_MAX:
        fh.seek(0)
        return fh.read(VERIFY_OUTPUT_MAX)
    fh.seek(size - VERIFY_OUTPUT_MAX - 1)
    data = fh.read(VERIFY_OUTPUT_MAX + 1)  # the byte before the window, then the window
    # the first line break from that byte on: when it is the byte before, the window's first line is whole
    breaks = [at for at in (data.find(b"\n"), data.find(b"\r")) if at != -1]
    return data[min(breaks) + 1:] if breaks else b""


def kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
            subprocess.run([taskkill, "/F", "/T", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def split_command(command: str) -> list[str]:
    """shlex on POSIX; on Windows, whitespace split honouring double quotes and
    keeping backslashes (paths)."""
    if os.name != "nt":
        return shlex.split(command)
    parts = []
    for token in shlex.split(command, posix=False):
        if len(token) >= 2 and token[0] == token[-1] == '"':
            token = token[1:-1]
        parts.append(token)
    return parts


# -- command line ------------------------------------------------------------------------------


def parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Renew one agent's FIELD delegation token before it expires.")
    p.add_argument("--agent", required=True)
    p.add_argument("--base", required=True, help="estate proxy root, e.g. http://127.0.0.1:18080")
    p.add_argument("--env-file")
    p.add_argument("--env-key")
    p.add_argument("--json-file")
    p.add_argument("--json-key")
    p.add_argument("--renew-within-days", type=int, default=7)
    p.add_argument("--ttl-days", type=int)
    p.add_argument("--lock-file")
    p.add_argument("--verify-cmd")
    p.add_argument("--verify-timeout", type=float, default=120.0)
    p.add_argument("--state-dir")
    p.add_argument("--secret-file")
    p.add_argument("--renew-revoked", action="store_true",
                   help="renew a token that was revoked (a revocation is otherwise refused)")
    p.add_argument("--check", action="store_true", help="print the decision; GETs only, no lock, no writes")
    return p.parse_args(argv)


def validate(a: argparse.Namespace, secret: str | None) -> None:
    env_pair, json_pair = (a.env_file, a.env_key), (a.json_file, a.json_key)
    if not ((all(env_pair) and not any(json_pair)) or (all(json_pair) and not any(env_pair))):
        raise Refused("give exactly one store: --env-file with --env-key, or --json-file with --json-key")
    if a.env_key and not ENV_KEY.fullmatch(a.env_key):
        raise Refused("--env-key must be a shell variable name")
    if not AGENT_ID.fullmatch(a.agent):
        raise Refused("--agent is not a registry agent id")
    if a.ttl_days is not None and not 1 <= a.ttl_days <= MAX_TTL_DAYS:
        raise Refused(f"--ttl-days must be 1..{MAX_TTL_DAYS}")
    if a.renew_within_days < 0:
        raise Refused("--renew-within-days must be >= 0")
    if not 1 <= a.verify_timeout <= 3600:
        raise Refused("--verify-timeout must be 1..3600 seconds")
    try:
        verify_argv = split_command(a.verify_cmd) if a.verify_cmd else []
    except ValueError:
        raise Refused("--verify-cmd cannot be split into arguments (unbalanced quotes)")
    if not a.check and not verify_argv:
        raise Refused("a renewal needs --verify-cmd: the old token is revoked only after the new one is proven")
    if not a.check and not any("{new_token}" in part for part in verify_argv):
        raise Refused("--verify-cmd must pass {new_token} to the verifier: a command that is not told which "
                      "token to prove proves nothing about it")
    parts = urllib.parse.urlsplit(a.base)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise Refused("--base must be http(s)://host[:port] with no credentials, query or fragment")
    if secret and parts.scheme != "https":
        host = parts.hostname or ""
        try:
            local = ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
        except ValueError:
            local = host == "localhost"
        if not local:
            raise Refused("the secret would travel in cleartext: use https:// or a loopback/private address")


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        secret = read_secret(args.secret_file)
        if secret:
            sys.stdout, sys.stderr = Redact(sys.stdout, secret), Redact(sys.stderr, secret)
        validate(args, secret)
        return Renewal(args, secret).run()
    except Refused as exc:
        say(f"refused: {exc}")
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
