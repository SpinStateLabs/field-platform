#!/usr/bin/env bash
# Run every SDK example against an ephemeral six-service stack (<90s).
# Boot → operator bootstrap → agent template → actions → usage → liveness
# → raw REST → teardown.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"
export PYTHONUTF8=1

WORK="$(mktemp -d)"
WORKW="$(cygpath -w "$WORK" 2>/dev/null || echo "$WORK")"
export FIELD_DATA_DIR="$WORKW"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
# Examples showcase real BLOCKs — opt into enforce (served default is log_only).
export FIELD_SENTINEL_MODE=enforce
sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004 FIELD_KILLSWITCH_URL=http://127.0.0.1:8005

python - <<'PY'
import time, httpx
for port in (8001, 8002, 8003, 8006, 8004, 8005):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
print("six services up")
PY

echo
echo "=== 04_bootstrap_operator.py (operator setup) ==="
BOOT_OUT=$(python "$HERE/04_bootstrap_operator.py")
echo "$BOOT_OUT" | sed '$d'
TOKEN=$(echo "$BOOT_OUT" | tail -1)

echo
echo "=== agent_template.py (the copy-paste skeleton) ==="
python "$HERE/agent_template.py" "$TOKEN"

echo
echo "=== 01_actions.py ==="
python "$HERE/01_actions.py" "$TOKEN"

echo
echo "=== 05_rest_api.sh (no SDK — raw REST) ==="
bash "$HERE/05_rest_api.sh" "$TOKEN"

echo
echo "=== 02_usage.py ==="
python "$HERE/02_usage.py"

echo
echo "=== 03_liveness.py ==="
python "$HERE/03_liveness.py"

echo
echo "all examples complete."
