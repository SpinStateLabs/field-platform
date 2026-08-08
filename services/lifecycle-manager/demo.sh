#!/usr/bin/env bash
# lifecycle-manager demo — <60s. Registry with one healthy agent and one
# orphan; sweep reports, then auto-kills only with the flag.
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
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_KILLSWITCH_URL=http://127.0.0.1:8005

python - <<'PY'
import time, httpx
from datetime import datetime, timedelta, timezone
for port in (8001, 8002, 8003, 8005):
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoicing",
    "owner": "AP Team Lead", "domain": "finance"})
httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "rogue-experiment", "name": "Forgotten growth experiment",
    "owner": "Departed Employee", "domain": "growth"})
httpx.post("http://127.0.0.1:8003/tokens", json={
    "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
    "scope": ["draft invoices"],
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=12)).isoformat()})
print("staged: healthy agent + orphan + token expiring in 12 days")
PY

cat > "$WORK/owners.csv" <<'CSV'
owner,department
AP Team Lead,finance
Controller Spin State,finance
CSV

echo
echo "=== 1. Sweep (report only — auto-kill is never a default) ==="
lifecycle sweep --roster "$WORK/owners.csv" --markdown "$WORK/sweep.md" || echo "(exit 3 — findings)"
cat "$WORK/sweep.md"

echo
echo "=== 2. Orphan still active? ==="
python -c "import httpx; print('  status:', httpx.get('http://127.0.0.1:8001/agents/rogue-experiment').json()['status'])"

echo
echo "=== 3. Sweep with --auto-kill-orphans (CHRO-authorized) ==="
lifecycle sweep --roster "$WORK/owners.csv" --auto-kill-orphans \
  --operator "CHRO quarterly sweep (demo)" >/dev/null || true
python -c "import httpx; print('  status:', httpx.get('http://127.0.0.1:8001/agents/rogue-experiment').json()['status'])"

echo
echo "demo complete."
