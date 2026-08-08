#!/usr/bin/env bash
# sealed-ledger demo — <60s. Appends, verifies, tampers, detects, exports.
set -euo pipefail

if ! command -v ledger >/dev/null 2>&1; then
  for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
    [ -x "$candidate/ledger" ] || [ -x "$candidate/ledger.exe" ] && PATH="$candidate:$PATH"
  done
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LEDGER="$WORK/events.jsonl"

echo "=== 1. Append five governance events ==="
ledger append agent.registered --agent-id invoicing-agent --path "$LEDGER" >/dev/null
ledger append token.mint --agent-id invoicing-agent --payload '{"scope":["draft invoices"]}' --path "$LEDGER" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-001","amount":1200}' --path "$LEDGER" >/dev/null
ledger append action --agent-id invoicing-agent --payload '{"invoice":"INV-002","amount":950}' --path "$LEDGER" >/dev/null
ledger append conformance.block --agent-id invoicing-agent --payload '{"clause_id":"D.scope"}' --path "$LEDGER" >/dev/null
echo "5 events appended."

echo
echo "=== 2. Verify — intact ==="
ledger verify --path "$LEDGER"

echo
echo "=== 3. Tamper: quietly change INV-001 from 1200 to 12 ==="
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
echo "demo complete."
