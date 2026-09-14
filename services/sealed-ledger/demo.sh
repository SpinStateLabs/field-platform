#!/usr/bin/env bash
# sealed-ledger demo — <60s. Appends, verifies, exports (filtered; unsigned and
# signed), re-verifies the bundles offline, tampers, detects, rotates,
# archives a closed segment (blocked first by a legal hold), and (F2) signs
# every event with a per-event key: a re-linked edit that beats plain verify
# is named by `verify --event-pubkey`, and require-signing refuses unsigned
# start-type appends while a kill still lands, stamped signing_failed.
set -euo pipefail

if ! command -v ledger >/dev/null 2>&1; then
  for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
    [ -x "$candidate/ledger" ] || [ -x "$candidate/ledger.exe" ] && PATH="$candidate:$PATH"
  done
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LEDGER="$WORK/events.jsonl"
# every verb below works on files: never delegate to a running service
unset FIELD_LEDGER_URL

echo "=== 1. Append six governance events ==="
ledger append agent.registered --agent-id invoicing-agent --path "$LEDGER" >/dev/null
ledger append token.mint --agent-id invoicing-agent --payload '{"scope":["draft invoices"]}' --path "$LEDGER" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-001","amount":1200}' --path "$LEDGER" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-002","amount":950}' --path "$LEDGER" >/dev/null
ledger append conformance.block --agent-id invoicing-agent --payload '{"clause_id":"D.scope"}' --path "$LEDGER" >/dev/null
ledger append action --agent-id timekeeping-agent --payload '{"hours":7}' --path "$LEDGER" >/dev/null
echo "6 events appended (5 invoicing-agent, then 1 timekeeping-agent)."

echo
echo "=== 2. Verify — intact ==="
ledger verify --path "$LEDGER"

bundle_dir() {  # bundle_dir from the export summary JSON on stdin
  python -c "import json,sys; print(json.load(sys.stdin)['bundle_dir'])"
}

echo
echo "=== 3. Auditor export filtered to invoicing-agent, UNSIGNED (what POST /export writes) ==="
UNSIGNED="$(ledger export --path "$LEDGER" --out-dir "$WORK/exports" --agent-id invoicing-agent | bundle_dir)"
ls "$UNSIGNED"
ledger verify-export "$UNSIGNED"

echo
echo "=== 4. Signed export (ledger export --sign-key), verified with the signer's public key ==="
python - "$WORK" <<'KEYS'
import pathlib, sys
from field_core.signing import generate_keypair
work = pathlib.Path(sys.argv[1])
for name in ("signer", "stranger"):
    private_pem, public_pem = generate_keypair()
    (work / f"{name}-private.pem").write_text(private_pem, encoding="ascii")
    (work / f"{name}-public.pem").write_text(public_pem, encoding="ascii")
KEYS
SIGNED="$(ledger export --path "$LEDGER" --out-dir "$WORK/exports" --agent-id invoicing-agent --sign-key "$WORK/signer-private.pem" | bundle_dir)"
ledger verify-export "$SIGNED" --pubkey "$WORK/signer-public.pem"

echo
echo "=== 5. The auditor's copy is edited: INV-002 amount 950 -> 95 in events.jsonl ==="
cp -r "$SIGNED" "$WORK/copy"
python - "$WORK/copy/events.jsonl" <<'EDIT'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
lines = p.read_text(encoding="utf-8").splitlines()
rec = json.loads(lines[3]); rec["payload"]["amount"] = 95
lines[3] = json.dumps(rec)
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
EDIT
if ledger verify-export "$WORK/copy" --pubkey "$WORK/signer-public.pem"; then
  echo "UNEXPECTED: the edited copy verified" >&2; exit 1
fi
echo "(exit 1 — the failing index is named)"

echo
echo "=== 6. Verified against the wrong public key ==="
if ledger verify-export "$SIGNED" --pubkey "$WORK/stranger-public.pem"; then
  echo "UNEXPECTED: the wrong key verified" >&2; exit 1
fi
echo "(exit 1 — not the signer's key)"

echo
echo "=== 7. Tamper the live ledger: quietly change INV-001 from 1200 to 12 ==="
python - "$LEDGER" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
lines = p.read_text(encoding="utf-8").splitlines()
rec = json.loads(lines[2]); rec["payload"]["amount"] = 12
lines[2] = json.dumps(rec)
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
ledger verify --path "$LEDGER" || echo "(exit 1 — the auditor sees exactly where)"

echo
echo "=== 8. Retention by rotation: close a segment (signed), keep one chain ==="
ROT="$WORK/rotating/events.jsonl"
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-003"}' --path "$ROT" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-004"}' --path "$ROT" >/dev/null
ledger rotate --offline --path "$ROT" --key "$WORK/signer-private.pem" --operator demo \
  --reason "quarter close" --anchors "$WORK/rotation-anchors.jsonl" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-005"}' --path "$ROT" >/dev/null
ls -A "$WORK/rotating"
ledger verify --path "$ROT" --anchors "$WORK/rotation-anchors.jsonl" --pubkey "$WORK/signer-public.pem"
ledger verify --path "$WORK/rotating/events-1.jsonl"

echo
echo "=== 9. Retention apply: a legal hold blocks it; released, the closed segment is archived ==="
export FIELD_DATA_DIR="$WORK"   # the archive dir must sit under FIELD_DATA_DIR, on the same filesystem
ARCHIVE="$WORK/ledger-archive"
ledger hold place --offline --path "$ROT" --by "General Counsel" --reason "litigation hold (demo)" >/dev/null
set +e
ledger retention apply --offline --path "$ROT" --days 0 --operator demo --archive-dir "$ARCHIVE" >/dev/null
code=$?
set -e
[ "$code" -eq 4 ] || { echo "UNEXPECTED: retention apply under a legal hold exited $code" >&2; exit 1; }
echo "(exit 4 — legal hold in place: nothing moved)"
ledger hold release --offline --path "$ROT" --by "General Counsel" >/dev/null
ledger retention apply --offline --path "$ROT" --days 0 --operator demo --archive-dir "$ARCHIVE" \
  | python -c "import json,sys; r=json.load(sys.stdin); print('archived segments:', r['archived_segments'], '| pending moves:', r['pending_moves'])"
ls -A "$ARCHIVE"
ledger verify --path "$ARCHIVE/events-1.jsonl" --pubkey "$WORK/signer-public.pem"

echo
echo "=== 10. Per-event signatures (F2): a SEPARATE sign key, loaded from FIELD_LEDGER_SIGN_KEY ==="
python - "$WORK" <<'KEYS'
import pathlib, sys
from field_core.signing import generate_keypair, key_fingerprint
work = pathlib.Path(sys.argv[1])
private_pem, public_pem = generate_keypair()
(work / "ledger-sign.pem").write_text(private_pem, encoding="ascii")
(work / "ledger-sign.pub.pem").write_text(public_pem, encoding="ascii")
print("sign key fingerprint:", key_fingerprint(public_pem))
KEYS
SIG="$WORK/signed/events.jsonl"
export FIELD_LEDGER_SIGN_KEY="$WORK/ledger-sign.pem"
ledger append agent.registered --agent-id invoicing-agent --path "$SIG" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-006","amount":300}' --path "$SIG" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-007","amount":450}' --path "$SIG" >/dev/null
ledger append conformance.allow --agent-id invoicing-agent --payload '{"action":"draft invoices"}' --path "$SIG" \
  | python -c "import json,sys; e=json.load(sys.stdin); print('appended, signature', e['signature'][:16] + '...', '(base64 Ed25519 over the hashed record)')"
ledger verify --path "$SIG" --event-pubkey "$WORK/ledger-sign.pub.pem"

echo
echo "=== 11. The attacker WITHOUT the key edits INV-006 300 -> 3 and re-links every later hash ==="
python - "$SIG" <<'RELINK'
import json, sys, pathlib
from field_core.ledger import compute_event_hash
p = pathlib.Path(sys.argv[1])
recs = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
recs[1]["payload"]["amount"] = 3
recs[1]["hash"] = compute_event_hash(recs[1])
for k in range(2, len(recs)):
    recs[k]["prev_hash"] = recs[k - 1]["hash"]
    recs[k]["hash"] = compute_event_hash(recs[k])
p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
RELINK
ledger verify --path "$SIG"
echo "(plain verify is blind to a re-linked chain — the documented limit)"
if ledger verify --path "$SIG" --event-pubkey "$WORK/ledger-sign.pub.pem"; then
  echo "UNEXPECTED: the re-linked edit verified under the sign key" >&2; exit 1
fi
echo "(exit 1 — the signature names the edited index)"
if ledger verify --path "$SIG" --event-pubkey "$WORK/stranger-public.pem" >/dev/null; then
  echo "UNEXPECTED: a stranger's key verified" >&2; exit 1
fi
echo "(wrong key: exit 1)"

echo
echo "=== 12. Require signing with NO key: a start-type append is refused, a kill still lands ==="
unset FIELD_LEDGER_SIGN_KEY
export FIELD_LEDGER_REQUIRE_SIGNING=1
REQ="$WORK/required/events.jsonl"
if ledger append registry.updated --agent-id invoicing-agent --path "$REQ" 2>/dev/null; then
  echo "UNEXPECTED: an unsigned start-type append was accepted" >&2; exit 1
fi
echo "(registry.updated refused: exit 2 — nothing written)"
ledger append kill.agent --agent-id invoicing-agent --payload '{"reason":"demo"}' --path "$REQ" \
  | python -c "import json,sys; e=json.load(sys.stdin); print('kill.agent appended, signing_failed =', e['signing_failed'], ', signature present =', 'signature' in e)"
unset FIELD_LEDGER_REQUIRE_SIGNING
ledger verify --path "$REQ" --event-pubkey "$WORK/ledger-sign.pub.pem"

echo
echo "demo complete."
