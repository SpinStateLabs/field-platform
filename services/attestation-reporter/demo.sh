#!/usr/bin/env bash
# attestation-reporter demo — <60s. Stages a small governed history, then
# renders the board pack.
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
print("staged: 1 agent, 1 token (14 d), 4 allows, 1 block, 1 drill")
PY

echo
echo "=== Render the board pack ==="
attest render --out "$WORK/pack" --period "Q3 2026 (demo)"

echo
echo "=== Every number, with its source (from the JSON) ==="
python - "$WORK" <<'PY'
import json, pathlib, sys
pack = json.loads((pathlib.Path(sys.argv[1]) / "pack" / "board-pack.json").read_text(encoding="utf-8"))
for section in pack["sections"]:
    print(f"[{section['title']}]")
    for m in section["metrics"]:
        value = "unavailable" if m["status"] == "unavailable" else f"{m['value']}{' ' + m['unit'] if m['unit'] else ''}"
        print(f"  {m['name']:44s} {value!s:16s} <- {m['source_query'][:70]}")
PY

echo
echo "demo complete."
