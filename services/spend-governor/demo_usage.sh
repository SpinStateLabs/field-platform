#!/usr/bin/env bash
# Token-usage governance demo — <60s. Cost from model+tokens, and the three
# rogue signals: off-list model, token burst, unpriced model.
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

ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_LEDGER_URL=http://127.0.0.1:8002
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_GOVERNOR_URL=http://127.0.0.1:8006
python - <<'PY'
import time, httpx
for p in (8002, 8006):
    for _ in range(60):
        try: httpx.get(f"http://127.0.0.1:{p}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
PY

show() { python -c "import sys,json; d=json.load(sys.stdin); s=d['status']; print(f\"  cost={s['token_cost_display']:>10} state={s['state']:8} rogue={[f['kind'] for f in d['rogue']]}\")"; }

echo "=== 1. Cap + policy: invoicing-agent may use ONLY Haiku, burst ceiling 200k tok/hr ==="
governor set-cap invoicing-agent --limit-cents 50000 --period daily >/dev/null
governor set-policy invoicing-agent --allowed-model claude-haiku-4-5 --token-rate-limit 200000 >/dev/null

echo
echo "=== 2. Normal usage — Haiku, priced, in policy ==="
governor usage invoicing-agent --model claude-haiku-4-5 --in 40000 --out 8000 | show

echo
echo "=== 3. Cost depends on the model: same tokens on Opus cost ~5x more ==="
python - <<'PY'
from field_core.pricing import DEFAULT_BOOK, units_to_usd_str
for m in ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"):
    u = DEFAULT_BOOK.cost_units(m, 40000, 8000)
    print(f"    {m:20s} 40k in / 8k out = {units_to_usd_str(u)}")
print("    (source:", DEFAULT_BOOK.source + ")")
PY

echo
echo "=== 4. ROGUE #1 — agent burns Opus tokens (off its allow-list) ==="
{ governor usage invoicing-agent --model claude-opus-4-8 --in 30000 --out 6000 || true; } | show

echo
echo "=== 5. ROGUE #2 — token burst past the 200k/hr ceiling ==="
governor usage invoicing-agent --model claude-haiku-4-5 --in 150000 --out 20000 | show || true

echo
echo "=== 6. ROGUE #3 — an unpriced model (cost cannot be governed) ==="
governor usage invoicing-agent --model gpt-4o-shadow --in 10000 --out 5000 | show || true

echo
echo "=== 7. Governor's view: usage, cost, model breakdown, rogue flags ==="
governor usage invoicing-agent | python -m json.tool

echo
echo "=== 8. Every finding is on the sealed ledger ==="
python - <<'PY'
import sys, httpx
sys.stdout.reconfigure(encoding="utf-8")
for e in httpx.get("http://127.0.0.1:8002/events").json():
    if e["event_type"].startswith("usage."):
        p = e["payload"]; print(f"  {e['event_type']:20s} model={p.get('model'):18} {p.get('detail','')[:60]}")
print("verify:", httpx.get("http://127.0.0.1:8002/verify").json()["ok"])
PY

echo
echo "demo complete."
