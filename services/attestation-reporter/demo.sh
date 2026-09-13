#!/usr/bin/env bash
# attestation-reporter demo — <60s. Stages a small governed history, renders
# the board pack for this quarter (derived from `date`, never a literal),
# signs it with a throwaway key, verifies it, and shows an edited copy refused.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
export FIELD_DATA_DIR="$WORK"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006

python - <<'PY'
import time, httpx
from datetime import datetime, timedelta, timezone
for port in (8001, 8002, 8003, 8006):
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoicing",
    "owner": "AP Team Lead", "domain": "finance"})
httpx.post("http://127.0.0.1:8003/tokens", json={
    "agent_id": "invoicing-agent", "granted_by": "Controller",
    "scope": ["draft invoices"],
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()})
for et in ("conformance.allow",) * 4 + ("conformance.block", "kill.drill.complete"):
    httpx.post("http://127.0.0.1:8002/events", json={
        "event_type": et, "agent_id": "invoicing-agent", "payload": {}})
# two daily sweeps flag the same agent: 2 sweep events, 1 distinct agent
for _ in range(2):
    httpx.post("http://127.0.0.1:8002/events", json={
        "event_type": "lifecycle.reattestation_due", "agent_id": "invoicing-agent",
        "payload": {"owner": "AP Team Lead", "days_stale": 91}})
# gate verification (rule-7 canary): one labelled row, in no governance figure
httpx.post("http://127.0.0.1:8002/events", json={
    "event_type": "conformance.allow", "agent_id": "canary-gb10", "payload": {}})
print("staged: 1 agent, 1 token (14 d), 4 allows, 1 block, 1 drill, "
      "2 re-attestation sweep events, 1 canary allow")
PY

# The window comes from the clock, never a literal quarter: this quarter, UTC.
MONTH=$((10#$(date -u +%m)))
PERIOD="$(date -u +%Y)-Q$(( (MONTH - 1) / 3 + 1 ))"
# A throwaway demo signing key, generated inside $WORK (deleted on exit).
python - "$WORK" <<'PY'
import pathlib, sys
from field_core.signing import generate_keypair
private_pem, public_pem = generate_keypair()
(pathlib.Path(sys.argv[1]) / "demo-signer.pem").write_text(private_pem, encoding="ascii")
(pathlib.Path(sys.argv[1]) / "demo-signer.pub.pem").write_text(public_pem, encoding="ascii")
PY

echo
echo "=== Render the board pack for $PERIOD, signed with a throwaway demo key (the signer name is a label, not a verified identity) ==="
attest render --out "$WORK/pack" --period "$PERIOD" \
  --signer "Demo Signer (throwaway demo key)" --sign-key "$WORK/demo-signer.pem"

echo
echo "=== Every number, with its source (from the JSON) ==="
python - "$WORK" <<'PY'
import json, pathlib, sys
pack = json.loads((pathlib.Path(sys.argv[1]) / "pack" / "board-pack.json").read_text(encoding="utf-8"))
w = pack["window"]
print(f"window: {w['kind']} {w['since']} .. {w['until']} | signed: {pack['signed']} by {pack['signer']}")
for section in pack["sections"]:
    print(f"[{section['title']}]")
    for m in section["metrics"]:
        value = "unavailable" if m["status"] == "unavailable" else f"{m['value']}{' ' + m['unit'] if m['unit'] else ''}"
        print(f"  {m['name'][:44]:44s} {value!s:16s} [{m['basis']}] <- {m['source_query'][:70]}")
PY

echo
echo "=== Verify the signature; then edit one number in a copy ==="
attest verify "$WORK/pack/board-pack.json" --pubkey "$WORK/demo-signer.pub.pem"
python - "$WORK" <<'PY'
import json, pathlib, sys
pack_dir = pathlib.Path(sys.argv[1]) / "pack"
pack = json.loads((pack_dir / "board-pack.json").read_text(encoding="utf-8"))
allow = next(m for s in pack["sections"] for m in s["metrics"] if m["name"] == "Conformance ALLOW verdicts")
allow["value"] += 1
(pack_dir / "edited.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")
print("edited copy: Conformance ALLOW verdicts +1")
PY
if attest verify "$WORK/pack/edited.json" --pubkey "$WORK/demo-signer.pub.pem"; then
  echo "an edited pack verified — this must never happen"; exit 1
fi
echo "(edited copy refused with exit 1, as designed)"

echo
echo "demo complete."
