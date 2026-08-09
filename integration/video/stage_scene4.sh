#!/usr/bin/env bash
# Stage Scene 4 of the capstone video ("Try to cheat it").
# Regenerates integration/video/scene4/ from scratch and self-tests every
# beat, so recording day is typing, not setup. Safe to re-run for retakes.
#
# Produces:
#   scene4/events.jsonl         genuine chain (keep pristine — for beat A)
#   scene4/tamper-me.jsonl      copy the presenter edits on camera (beat B)
#   scene4/forged-events.jsonl  self-consistent forgery, refusal erased (beat C)
#   scene4/anchors.jsonl        signed anchor of the genuine chain
#   scene4/keys/anchor-*.pem    demo keypair (regenerated; never committed)
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found (see STATE.md)"; exit 1; }
PATH="$VENVBIN:$PATH"

HERE="$(cd "$(dirname "$0")" && pwd)"
S4="$HERE/scene4"
rm -rf "$S4"
mkdir -p "$S4/keys"

echo "── 1. Genuine ledger: an invoicing afternoon, refusal included ──"
L="$S4/events.jsonl"
ledger append conformance.allow --agent-id invoicing-agent \
  --payload '{"action":"draft invoices","invoice":"INV-001","amount":1200}' --path "$L" >/dev/null
ledger append conformance.allow --agent-id invoicing-agent \
  --payload '{"action":"draft invoices","invoice":"INV-002","amount":950}' --path "$L" >/dev/null
ledger append conformance.allow --agent-id invoicing-agent \
  --payload '{"action":"draft invoices","invoice":"INV-003","amount":1250}' --path "$L" >/dev/null
ledger append conformance.block --agent-id invoicing-agent \
  --payload '{"action":"transfer funds","clause_id":"D.scope"}' --path "$L" >/dev/null
ledger append kill.agent --agent-id invoicing-agent \
  --payload '{"operator":"CISO on-call (demo)","reason":"scope probing"}' --path "$L" >/dev/null
echo "   5 events (3 allows, 1 BLOCK D.scope, 1 kill)"

echo "── 2. Keypair + signed anchor of the genuine chain ──"
fedbroker keygen --out-dir "$S4/keys" --name anchor >/dev/null
ledger anchor --path "$L" --anchors "$S4/anchors.jsonl" \
  --key "$S4/keys/anchor-private.pem" >/dev/null
echo "   anchored (chain length 5, Ed25519-signed)"

echo "── 3. tamper-me.jsonl — the presenter's on-camera copy ──"
cp "$L" "$S4/tamper-me.jsonl"

echo "── 4. forged-events.jsonl — the smart attacker's rewrite ──"
python - "$S4" <<'PY'
import json, pathlib, sys
from field_core.ledger import GENESIS_HASH, make_event

s4 = pathlib.Path(sys.argv[1])
originals = [json.loads(line) for line in
             (s4 / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

# The attacker rebuilds the ENTIRE chain, erasing the refusal and the kill:
# the BLOCK becomes a routine allow, the kill becomes a harmless heartbeat.
forged, prev = [], GENESIS_HASH
for rec in originals:
    payload, etype = dict(rec["payload"]), rec["event_type"]
    if etype == "conformance.block":
        etype, payload = "conformance.allow", {"action": "draft invoices",
                                               "invoice": "INV-004", "amount": 1100}
    if etype == "kill.agent":
        etype, payload = "conformance.allow", {"action": "read timesheets"}
    ev = make_event(etype, payload, prev_hash=prev,
                    agent_id=rec["agent_id"], ts=rec["ts"])
    forged.append(ev); prev = ev.hash

(s4 / "forged-events.jsonl").write_text(
    "\n".join(e.model_dump_json() for e in forged) + "\n", encoding="utf-8")
print("   forgery built: refusal and kill erased, chain fully re-hashed")
PY

echo "── 5. Self-test every beat (what the camera must see) ──"
echo "  [A] genuine chain:"
ledger verify --path "$L" --anchors "$S4/anchors.jsonl" \
  --pubkey "$S4/keys/anchor-public.pem" | sed 's/^/      /'
echo "  [B] one-keystroke tamper (simulated on a scratch copy):"
python - "$S4" <<'PY'
import json, pathlib, sys
s4 = pathlib.Path(sys.argv[1])
lines = (s4 / "tamper-me.jsonl").read_text(encoding="utf-8").splitlines()
rec = json.loads(lines[0]); rec["payload"]["amount"] = 12   # 1200 -> 12
lines[0] = json.dumps(rec)
(s4 / ".selftest-tampered.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
ledger verify --path "$S4/.selftest-tampered.jsonl" | sed 's/^/      /' || true
rm -f "$S4/.selftest-tampered.jsonl"
echo "  [C] wholesale forgery — naive check vs anchored check:"
ledger verify --path "$S4/forged-events.jsonl" | sed 's/^/      /' || true
ledger verify --path "$S4/forged-events.jsonl" --anchors "$S4/anchors.jsonl" \
  --pubkey "$S4/keys/anchor-public.pem" | sed 's/^/      /' || true

echo
echo "scene4/ staged. On camera, follow integration/video/CUE-CARD.md."