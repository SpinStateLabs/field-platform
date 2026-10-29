#!/usr/bin/env python3
"""operator_keygen - make a FIELD operator key on YOUR machine (Phase G).

    operator_keygen.py [--key-file PATH] [--operator-id ID --scopes a,b
                        [--alias NAME ...] [--event-prefix P ...]
                        --add-to operators.json]
    operator_keygen.py --check operators.json

* The key is generated here (secrets.token_urlsafe) and shown ONCE, on stdout,
  or written to --key-file (created exclusively, mode 0600 where the OS has it)
  instead of being printed. It is never logged, never written anywhere else,
  never put in an error message. Do not run this in a shared session: whoever
  sees the terminal sees the key.
* What you register is the sha256, printed on its own line. With --add-to the
  entry {operator_id, key_sha256, status, created_at, scopes} is added to the
  operators file; the key itself is not written to that file. The file is
  replaced atomically (a fully written temp file in the same directory, then a
  rename), so a service reading it per request never sees a truncated file,
  and nothing is written if the result would not pass the registry checks.
* --check FILE runs the same validation the services apply under REQUIRE
  (``status`` present and exactly active/revoked, 64 lower-case hex
  ``key_sha256``, well-formed scopes/names/event_prefixes, no colliding ids or
  aliases, at least one active row) and prints ids, status and fingerprints
  only (an id carrying the key prefix prints as "(not shown)", and an error
  names a row by number and printable id only, never a status value or a
  key-shaped id). Exit 0 = valid, 1 = invalid, 2 = usage error.
  It makes no key. On a format 2 file (key rotation) it also prints the
  format, generation, each row's rotation and, per key slot (CURRENT, NEXT),
  the 8-hex fingerprint and the validity window: still never a full hash.
  --add-to refuses a format 2 file (the rotator writes those).
* Use the key as the x-field-operator-key header (or FIELD_OPERATOR_KEY, or a
  file named by FIELD_OPERATOR_KEY_FILE).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "field-core" / "src"))
from field_core.operator_auth import (  # noqa: E402
    ACTIONS, FORMAT_2, NOT_SHOWN, REJECTED_SCOPES, _OPERATOR_RE, RegistryUnavailable,
    decode_registry_document, format_time, key_fingerprint, key_sha256, parse_registry, parse_registry_doc, printable_id,
    valid_event_prefix)


def generate_key() -> str:
    return "fok_" + secrets.token_urlsafe(32)


def _default_mode() -> int:
    um = os.umask(0)
    os.umask(um)
    return 0o666 & ~um


def atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically: write a temp file in the SAME
    directory, flush and fsync it, keep the old file's permission bits (or the
    umask default for a new file), then os.replace it over the target. A
    reader sees the old content or the new content, never a partial file; on
    any failure the temp file is removed and the target is untouched."""
    path = Path(path)
    directory = path.parent if str(path.parent) else Path(".")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else _default_mode()
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if hasattr(os, "O_DIRECTORY"):            # POSIX: make the rename durable
        try:
            dfd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass


def _read_doc(path: Path):
    """The decoded operators document (BOM tolerated, as the services read it)."""
    try:
        return decode_registry_document(path.read_bytes())
    except RegistryUnavailable as exc:
        raise SystemExit(f"error: {path}: {exc}")


def add_entry(path: Path, operator_id: str, sha: str, scopes: list[str],
              aliases: list[str] | None = None,
              event_prefixes: list[str] | None = None) -> None:
    write_registry(path, prepare_entry(path, operator_id, sha, scopes, aliases, event_prefixes))


def prepare_entry(path: Path, operator_id: str, sha: str, scopes: list[str],
                  aliases: list[str] | None = None,
                  event_prefixes: list[str] | None = None) -> Any:
    """The document ``write_registry`` will write, or a SystemExit when it must not be: every refusal of
    --add-to is decided here, before main() writes or prints a key (C-235)."""
    doc = _read_doc(path) if path.exists() else []
    if isinstance(doc, dict) and doc.get("format") == FORMAT_2:
        raise SystemExit("error: --add-to does not edit a format 2 operators file (its rows "
                         "need rotation and key expiry fields; the rotator writes it)")
    rows = doc.get("operators", []) if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise SystemExit("error: the operators file is not a list of operators")
    if any(isinstance(r, dict) and r.get("operator_id") == operator_id for r in rows):
        raise SystemExit(f"error: operator id '{operator_id}' already exists in the file "
                         "(a duplicate id makes the whole registry unloadable). To rotate "
                         "a key, set the old row's status to 'revoked' and register the "
                         "new key under a NEW operator id")
    new_row = {
        "operator_id": operator_id, "key_sha256": sha, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scopes": scopes,
        # display names that manifests' authorized_operators may use for this
        # human; only the key holder's owner (Don) decides what goes here
        "names": list(aliases or []),
    }
    if event_prefixes:
        new_row["event_prefixes"] = list(event_prefixes)
    new_rows = rows + [new_row]
    out = {**doc, "operators": new_rows} if isinstance(doc, dict) else new_rows
    try:
        # validate the WHOLE document that will be written, not only its rows:
        # a format 1 dict carrying a top-level field the services refuse (a
        # format 2 name, or a format value other than the integer 1 or 2) is
        # never written back (review F4)
        parse_registry(out, require_active=False)
    except RegistryUnavailable as exc:
        raise SystemExit(f"error: refusing to write an invalid registry: {exc}")
    return out


def write_registry(path: Path, out: Any) -> None:
    atomic_write_text(path, json.dumps(out, indent=2) + "\n")


def check_file(path: Path) -> int:
    """--check: the registry validation, ids/status/fingerprints only."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"error: {path}: unreadable ({type(exc).__name__})", file=sys.stderr)
        return 1
    try:
        doc = decode_registry_document(data)
    except RegistryUnavailable as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        return 1
    try:
        parsed = parse_registry_doc(doc, require_active=True)
    except RegistryUnavailable as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        return 1
    if parsed.format == FORMAT_2:
        return _print_format2(path, data, parsed)
    rows = parsed.rows
    given = doc.get("operators") if isinstance(doc, dict) else doc
    active = sum(1 for r in rows if r["status"] == "active")
    print(f"operators file: {path}")
    print(f"file sha256 (first 16 hex): {hashlib.sha256(data).hexdigest()[:16]}")
    print(f"rows: {len(rows)} (active {active}, revoked {len(rows) - active})")
    # PG0-CORE-R1-10: an id that could be a key (the key prefix) is never printed
    ids = [r["operator_id"] if printable_id(r["operator_id"]) else NOT_SHOWN for r in rows]
    width = max(len(i) for i in ids)
    for oid, r in zip(ids, rows):
        print(f"  {oid:<{width}}  {r['status']:<7}  fingerprint {r['key_sha256'][:8]}")
    dropped = len(given) - len(rows)
    if dropped:
        print(f"warning: {dropped} row(s) with an unencodable operator_id are ignored by the services")
    print("OK: passes the registry validation the services apply under REQUIRE")
    return 0


def _window_state(now: float, not_before: int | None, not_after: int | None) -> str:
    if not_before is not None and now < not_before:
        return "not yet valid"
    if not_after is not None and now >= not_after:
        return "EXPIRED"
    return "valid now"


def _print_format2(path: Path, data: bytes, parsed) -> int:
    """--check on a format 2 file: ids, slots, windows and fingerprints only
    (8 hex, as for format 1; never a full hash, never a passkey value)."""
    from field_core import operator_auth as oa

    now = oa.clock()
    rows = parsed.rows
    active = sum(1 for r in rows if r["status"] == "active")
    print(f"operators file: {path}")
    print(f"file sha256 (first 16 hex): {hashlib.sha256(data).hexdigest()[:16]}")
    print(f"format: 2  generation: {parsed.generation}")
    if parsed.issued_at is not None or parsed.issued_by is not None:
        print(f"issued: {format_time(parsed.issued_at) if parsed.issued_at is not None else '-'}"
              f" by {parsed.issued_by or '-'}")
    print(f"checked at: {format_time(int(now))}")
    print(f"rows: {len(rows)} (active {active}, revoked {len(rows) - active})")
    ids = [r["operator_id"] if printable_id(r["operator_id"]) else NOT_SHOWN for r in rows]
    width = max(len(i) for i in ids)
    for oid, r in zip(ids, rows):
        print(f"  {oid:<{width}}  {r['status']:<7}  rotation {r['rotation']}"
              f"  auth {','.join(r['auth'])}  passkeys {len(r['passkeys'])}")
        if r["key_not_after"] is None:
            print(f"    current  fingerprint {r['key_sha256'][:8]}  no expiry (sealed)")
        else:
            print(f"    current  fingerprint {r['key_sha256'][:8]}  until "
                  f"{format_time(r['key_not_after'])}  "
                  f"{_window_state(now, None, r['key_not_after'])}")
        nk = r["next_key"]
        if nk is not None:
            print(f"    next     fingerprint {nk['key_sha256'][:8]}  from "
                  f"{format_time(nk['not_before'])} until {format_time(nk['not_after'])}  "
                  f"{_window_state(now, nk['not_before'], nk['not_after'])}")
    print("OK: passes the registry validation the services apply under REQUIRE (format 2)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--key-file", help="write the key here (exclusive create, 0600) instead of printing it")
    ap.add_argument("--operator-id")
    ap.add_argument("--scopes", default=None,
                    help="comma list of: * " + ",".join(sorted(ACTIONS - REJECTED_SCOPES))
                    + " (default *)")
    ap.add_argument("--add-to", help="operators.json to add the sha256 entry to")
    ap.add_argument("--alias", action="append", default=[],
                    help="a display name this operator answers to in a manifest's "
                    "authorized_operators (repeatable; exact, case-sensitive), "
                    'e.g. --alias "Don Hagell" --alias "Don Hagell, Spin State Labs"')
    ap.add_argument("--event-prefix", action="append", default=[],
                    help="with the ledger_attribute scope: an event-type prefix (ending in "
                    "'.', e.g. registry.) whose events may carry the operator fields "
                    "(repeatable)")
    ap.add_argument("--check", metavar="FILE",
                    help="validate an operators file and print ids, status and fingerprints "
                    "only; makes no key")
    a = ap.parse_args(argv)

    if a.check:
        if (a.key_file or a.operator_id or a.add_to or a.alias or a.event_prefix
                or a.scopes is not None):
            print("error: --check takes no other option", file=sys.stderr)
            return 2
        return check_file(Path(a.check))

    scopes = [s.strip() for s in (a.scopes or "*").split(",") if s.strip()]
    bad = [s for s in scopes if s != "*" and (s not in ACTIONS or s in REJECTED_SCOPES)]
    if bad or not scopes:
        print(f"error: unknown scope(s) {bad or '(none)'}", file=sys.stderr)
        return 2
    if any(not (0 < len(n) <= 128) for n in a.alias):
        print("error: an alias must be 1-128 characters", file=sys.stderr)
        return 2
    if any(not valid_event_prefix(p) for p in a.event_prefix):
        print("error: an --event-prefix is dotted lower-case segments ending in '.' "
              "(e.g. registry.), at most 64 characters, never operator.", file=sys.stderr)
        return 2
    if a.event_prefix and "ledger_attribute" not in scopes:
        print("error: --event-prefix applies only to the ledger_attribute scope", file=sys.stderr)
        return 2
    if "ledger_attribute" in scopes and not a.event_prefix:
        print("error: ledger_attribute needs at least one --event-prefix "
              "(without one it attributes nothing)", file=sys.stderr)
        return 2
    if a.add_to and not a.operator_id:
        print("error: --add-to needs --operator-id", file=sys.stderr)
        return 2
    if a.operator_id and not _OPERATOR_RE.match(a.operator_id):
        print("error: --operator-id must match [A-Za-z0-9._@-]{1,64}", file=sys.stderr)
        return 2

    key = generate_key()
    sha = key_sha256(key)
    # C-235: every refusal of --add-to (duplicate id, shared alias, a format 2 file, an invalid result) comes
    # before the key is written or printed, so a refused run never leaves a key whose hash was not registered
    registry = prepare_entry(Path(a.add_to), a.operator_id, sha, scopes, a.alias, a.event_prefix) if a.add_to else None
    if a.key_file:
        fd = os.open(a.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key + "\n")
        print(f"key written to {a.key_file} (not printed)")
    else:
        print("KEY (shown once - store it now, it cannot be recovered):")
        print(key)
    print(f"key_sha256: {sha}")
    print(f"fingerprint: {key_fingerprint(key)}")
    if registry is not None:
        write_registry(Path(a.add_to), registry)
        print(f"registered sha256 for '{a.operator_id}' in {a.add_to}")
    else:
        print("register this sha256 in the operators file "
              "(operator_id, key_sha256, status, created_at, scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
