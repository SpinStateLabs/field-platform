#!/usr/bin/env python3
"""operator_keygen - make a FIELD operator key on YOUR machine (Phase G).

    operator_keygen.py [--key-file PATH] [--operator-id ID --scopes a,b
                        --add-to operators.json]

* The key is generated here (secrets.token_urlsafe) and shown ONCE, on stdout,
  or written to --key-file (created exclusively, mode 0600 where the OS has it)
  instead of being printed. It is never logged, never written anywhere else,
  never put in an error message. Do not run this in a shared session: whoever
  sees the terminal sees the key.
* What you register is the sha256, printed on its own line. With --add-to the
  entry {operator_id, key_sha256, status, created_at, scopes} is added to the
  operators file; the key itself is not written to that file.
* Use the key as the x-field-operator-key header (or FIELD_OPERATOR_KEY).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "field-core" / "src"))
from field_core.operator_auth import (  # noqa: E402
    ACTIONS, _OPERATOR_RE, key_fingerprint, key_sha256)


def generate_key() -> str:
    return "fok_" + secrets.token_urlsafe(32)


def add_entry(path: Path, operator_id: str, sha: str, scopes: list[str],
              aliases: list[str] | None = None) -> None:
    rows = []
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("operators", [])
    if any(r.get("operator_id") == operator_id and r.get("status") == "active" for r in rows):
        raise SystemExit(f"error: operator '{operator_id}' already has an active key; "
                         "revoke it first (set status to 'revoked')")
    rows.append({
        "operator_id": operator_id, "key_sha256": sha, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scopes": scopes,
        # display names that manifests' authorized_operators may use for this
        # human; only the key holder's owner (Don) decides what goes here
        "names": list(aliases or []),
    })
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--key-file", help="write the key here (exclusive create, 0600) instead of printing it")
    ap.add_argument("--operator-id")
    ap.add_argument("--scopes", default="*", help="comma list of: * " + ",".join(sorted(ACTIONS)))
    ap.add_argument("--add-to", help="operators.json to add the sha256 entry to")
    ap.add_argument("--alias", action="append", default=[],
                    help="a display name this operator answers to in a manifest's "
                    "authorized_operators (repeatable; exact, case-sensitive), "
                    'e.g. --alias "Don Hagell" --alias "Don Hagell, Spin State Labs"')
    a = ap.parse_args(argv)

    scopes = [s.strip() for s in a.scopes.split(",") if s.strip()]
    bad = [s for s in scopes if s != "*" and s not in ACTIONS]
    if bad or not scopes:
        print(f"error: unknown scope(s) {bad or '(none)'}", file=sys.stderr)
        return 2
    if any(not (0 < len(n) <= 128) for n in a.alias):
        print("error: an alias must be 1-128 characters", file=sys.stderr)
        return 2
    if a.add_to and not a.operator_id:
        print("error: --add-to needs --operator-id", file=sys.stderr)
        return 2
    if a.operator_id and not _OPERATOR_RE.match(a.operator_id):
        print("error: --operator-id must match [A-Za-z0-9._@-]{1,64}", file=sys.stderr)
        return 2

    key = generate_key()
    sha = key_sha256(key)
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
    if a.add_to:
        add_entry(Path(a.add_to), a.operator_id, sha, scopes, a.alias)
        print(f"registered sha256 for '{a.operator_id}' in {a.add_to}")
    else:
        print("register this sha256 in the operators file "
              "(operator_id, key_sha256, status, created_at, scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
