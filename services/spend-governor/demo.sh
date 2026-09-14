#!/usr/bin/env bash
# spend-governor demo — <60s. Cap from the financial-agent template,
# spend toward it, watch ESCALATE fire before BLOCK.
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

governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_GOVERNOR_URL=http://127.0.0.1:8006
python - <<'PY'
import time, httpx
for _ in range(60):
    try:
        httpx.get("http://127.0.0.1:8006/health", timeout=0.5); break
    except Exception: time.sleep(0.25)
PY

echo "=== 1. Cap from the shipped financial-agent template: USD 500/day ==="
field templates --show financial-agent --out "$WORK/fin.yaml"
governor set-cap invoicing-agent --from-manifest "$WORK/fin.yaml" | python -m json.tool

echo
echo "=== 2. Spend \$350 — OK ==="
governor spend invoicing-agent --cents 35000 | python -c "import sys,json; d=json.load(sys.stdin); print(d['state'], '-', d['detail'])"

echo
echo "=== 3. Spend \$60 more (\$410 = 82%) — ESCALATE before the cap ==="
governor spend invoicing-agent --cents 6000 | python -c "import sys,json; d=json.load(sys.stdin); print(d['state'], '-', d['detail'])"
governor escalations | python -m json.tool

echo
echo "=== 4. Spend \$90 more (\$500 = cap) — BLOCK ==="
governor spend invoicing-agent --cents 9000 | python -c "import sys,json; d=json.load(sys.stdin); print(d['state'], '-', d['detail'])" || echo "(exit 1 — sentinel would refuse the action)"

echo
echo "=== 5. Throttle: the manifest allows 2 'read timesheets' per hour ==="
python - "$WORK/fin.yaml" "$WORK/reader.yaml" <<'PY'
import sys, yaml
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
data["enforcement"]["rate_limits"].append({"action": "read timesheets", "max": 2, "period": "hourly"})
yaml.safe_dump(data, open(sys.argv[2], "w", encoding="utf-8"), sort_keys=False)
PY
governor set-cap reader-agent --from-manifest "$WORK/reader.yaml" >/dev/null   # stderr: 1 enforced + the loud session warning
for n in 1 2; do
  governor spend reader-agent --actions 1 --action "read timesheets" | python -c "import sys,json; d=json.load(sys.stdin); print('after read', '$n', '(recorded):', d['state'], '-', d['detail'])"
done
governor status reader-agent --action "read timesheets" | python -c "import sys,json; d=json.load(sys.stdin); print(d['state'], '- retry_after_seconds', d['retry_after_seconds'], '(a 3rd read: the sentinel would BLOCK E.rate_limit)')"
governor status reader-agent --action "draft invoices" | python -c "import sys,json; d=json.load(sys.stdin); print('draft invoices:', d['state'], '(no limit on that action)')"

echo
echo "demo complete."
