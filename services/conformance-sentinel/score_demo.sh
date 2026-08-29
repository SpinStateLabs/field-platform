#!/usr/bin/env bash
# S2 scorecard demo — <60s. Boots an ephemeral estate with the sentinel in its
# SERVED DEFAULT mode (log_only — deliberately unset), runs the 100-seed suite
# via `sentinel score`, and captures the sourced scorecard artifact.
# The ledger-unreachable group is enabled because this stack owns its ledger
# process (never do that to a shared estate).
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${1:-$HERE/../../docs/capstone-evidence}"
mkdir -p "$OUT_DIR"

WORK="$(mktemp -d)"
export FIELD_DATA_DIR="$WORK" FIELD_MANIFEST_DIR="$WORK"
unset FIELD_SENTINEL_MODE   # served default IS the subject under test
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & LEDGER_PID=$!; PIDS+=($LEDGER_PID)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004

python - <<'PY'
import time, httpx
for port in (8001, 8002, 8003, 8004, 8006):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
PY

echo "=== sentinel /health (served default must be log_only) ==="
python -c "import httpx; print(' ', httpx.get('http://127.0.0.1:8004/health').json())"

echo
echo "=== sentinel score — 100 seeds, ledger-unreachable group enabled ==="
SECONDS=0
(cd "$HERE" && sentinel score \
  --manifest-dir "$WORK" \
  --ledger-down-cmd "kill $LEDGER_PID" \
  --out-md "$OUT_DIR/sentinel-scorecard-s2.md" \
  --out-json "$OUT_DIR/sentinel-scorecard-s2.json")
echo "score run took ${SECONDS}s"

echo
echo "artifacts:"
echo "  $OUT_DIR/sentinel-scorecard-s2.md"
echo "  $OUT_DIR/sentinel-scorecard-s2.json"
echo "demo complete."
