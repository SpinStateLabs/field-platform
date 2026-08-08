#!/usr/bin/env bash
# kill-switch demo — <60s. Boots registry+ledger+killswitch, runs a timed
# drill, then a real domain kill.
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
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_KILLSWITCH_URL=http://127.0.0.1:8005

python - <<'PY'
import time, httpx
for port in (8001, 8002, 8005):
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
for aid, dom in (("invoicing-agent","finance"), ("forecast-agent","finance")):
    httpx.post("http://127.0.0.1:8001/agents", json={
        "agent_id": aid, "name": aid, "owner": "Controller", "domain": dom})
print("registered: invoicing-agent, forecast-agent (domain=finance)")
PY

echo
echo "=== 1. The 2 a.m. drill: kill, verify, restore — measured ==="
killswitch drill invoicing-agent --operator "CISO on-call" | python -m json.tool

echo
echo "=== 2. Heartbeat while alive ==="
killswitch heartbeat invoicing-agent

echo
echo "=== 3. Real domain kill: finance ==="
killswitch domain finance --operator "CISO on-call" --reason "credential leak drill" | python -m json.tool

echo
echo "=== 4. Heartbeat now says stop (exit 1) ==="
killswitch heartbeat invoicing-agent || echo "(agent told to halt)"

echo
echo "=== 5. Ledger trail ==="
python - <<'PY'
import httpx
for e in httpx.get("http://127.0.0.1:8002/events").json():
    print(f"  {e['event_type']:22s} agent={e['agent_id']}")
PY

echo
echo "demo complete."
