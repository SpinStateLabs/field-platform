#!/usr/bin/env python3
"""d16_record_check - read-only check that the D16 positive write is recorded in the ledger (Phase G G27).

    python tools/d16_record_check.py --operator-id ID --events FILE
    python tools/d16_record_check.py --operator-id ID --base URL --secret-file PATH

D16 is Don's positive write: one guarded write made with his own operator key. The ledger row that proves it carries
``operator_id_authenticated`` (the id the server authenticated from the key), ``operator_claimed`` (the name the caller
claimed) and ``operator_key_fp`` (8 hex of the key fingerprint). A row that has only the claimed name proves nothing:
it is what an open guard records.

Limit: the three fields are server-side attribution, not a cryptographic signature, and the tool does not read the operator
mode. The row proves the write only when the operator layer was NOT OFF when the row was written (LOG-ONLY or ENFORCE):
under OFF the ledger stores a payload untouched, so any perimeter-secret holder can write a row that passes this check.
A service holding ``ledger_attribute`` for the event type can also write these fields by design.

This tool only READS. It finds rows by the authenticated id and prints ids, the event type and the first 12
characters of the event hash, never a payload, a key, a key hash or the perimeter secret. Docs step for Don: make the
one write yourself (the runbook's live-verification step), then run this with your operator id; the session never
needs your key.

Exit status: 0 a signed authenticated row was found, 1 none was (or only claimed-name rows), 2 usage error or the
ledger could not be read. Standard library only (``--base`` uses tools/estate_probe.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_OP_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_FP_RE = re.compile(r"^[0-9a-f]{8}$")
_HASH_RE = re.compile(r"^[0-9a-f]{12,128}$")
HASH_PREFIX = 12


def _payload(ev: Any) -> dict:
    p = ev.get("payload") if isinstance(ev, dict) else None
    return p if isinstance(p, dict) else {}


def _shown_id(value: Any) -> str:
    """A value for display: only a plain id spelling, and never a key (fok_ prefix)."""
    return value if isinstance(value, str) and _OP_RE.fullmatch(value) and not value.startswith("fok_") else "(not shown)"


def check_events(events: list, operator_id: str) -> tuple[bool, list[str]]:
    """(ok, output lines). ok only when a row has the authenticated id == operator_id, a non-empty claimed name and a
    well-formed key fingerprint. Rows that carry the id only as a claim are reported as not proof."""
    lines: list[str] = []
    proof = 0
    claimed_only = 0
    for ev in events:
        p = _payload(ev)
        authenticated = p.get("operator_id_authenticated")
        claimed = p.get("operator_claimed")
        fp = p.get("operator_key_fp")
        if authenticated == operator_id:
            has_claim = isinstance(claimed, str) and claimed != ""
            has_fp = isinstance(fp, str) and _FP_RE.fullmatch(fp) is not None
            h = ev.get("hash") if isinstance(ev, dict) else None
            hp = h[:HASH_PREFIX] if isinstance(h, str) and _HASH_RE.fullmatch(h) else "(no hash)"
            et = _shown_id(ev.get("event_type") if isinstance(ev, dict) else None)
            good = has_claim and has_fp
            lines.append(f"[{'PASS' if good else 'FAIL'}] {et} row: authenticated id {_shown_id(authenticated)}, "
                         f"claimed name {'present' if has_claim else 'MISSING'}, "
                         f"key fingerprint {'well-formed' if has_fp else 'MISSING'}, event hash {hp}")
            proof += good
        elif claimed == operator_id:
            claimed_only += 1
    if claimed_only:
        lines.append(f"[INFO] {claimed_only} row(s) name {_shown_id(operator_id)} as a CLAIM only (no authenticated id): "
                     "not proof of the positive write")
    ok = proof > 0
    lines.append(f"[{'PASS' if ok else 'FAIL'}] D16 positive write recorded for {_shown_id(operator_id)}: "
                 f"{proof} signed authenticated row(s)")
    return ok, lines


def _load_events(path: str) -> list | None:
    try:
        raw = json.loads(sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(raw, dict):
        raw = raw.get("events")
    return raw if isinstance(raw, list) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="d16_record_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--operator-id", required=True, help="the operator id Don authenticated as (an id, never a key)")
    ap.add_argument("--events", help="a JSON file (or - for stdin) holding the ledger events list")
    ap.add_argument("--base", help="estate base URL; reads GET /ledger/events (needs --secret-file)")
    ap.add_argument("--secret-file", help="file holding the perimeter secret; read, sent as a header, never printed")
    args = ap.parse_args(argv)
    if not _OP_RE.fullmatch(args.operator_id) or args.operator_id.startswith("fok_"):
        print("error: --operator-id must be an operator id, not a key")
        return 2
    if bool(args.events) == bool(args.base):
        print("error: give exactly one of --events or --base")
        return 2
    if args.events:
        events = _load_events(args.events)
    else:
        if not args.secret_file:
            print("error: --base needs --secret-file")
            return 2
        import estate_probe as ep
        try:
            secret = Path(args.secret_file).read_text(encoding="utf-8").strip()
        except OSError:
            print("error: the secret file cannot be read")
            return 2
        status, body = ep.Estate(args.base, secret).call("GET", "/ledger/events")
        events = body if status == 200 and isinstance(body, list) else None
    if events is None:
        print("error: the ledger events could not be read")
        return 2
    ok, lines = check_events(events, args.operator_id)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
