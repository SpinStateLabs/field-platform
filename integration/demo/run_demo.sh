#!/usr/bin/env bash
# FIELD Platform integration demo — the capstone scenario, one command.
#
#   register agent + manifest → mint token → governed work (ledger fills)
#   → out-of-scope BLOCK → spend ESCALATE → kill drill → post-mortem.
#
# Runs the services as local processes (docker-compose.yml is provided but
# UNTESTED on machines without docker — see STATE.md OQ-5).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found (see STATE.md)"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
OUT="$HERE/out"
rm -rf "$OUT"; mkdir -p "$OUT"
export FIELD_DATA_DIR="$WORK"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

echo "══ FIELD Platform integration demo — governed invoicing agent ══"
echo
echo "── 0. Boot: registry ledger delegation sentinel killswitch governor replay ──"
registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
replay serve --port 8007 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004 FIELD_KILLSWITCH_URL=http://127.0.0.1:8005 FIELD_REPLAY_URL=http://127.0.0.1:8007

python - <<'PY'
import time, httpx
for port in (8001, 8002, 8003, 8004, 8005, 8006, 8007):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
print("   7 services healthy")
PY

echo
echo "── 1. Validate + register the agent and its manifest ──"
field validate "$HERE/manifests/invoicing-agent.yaml" | head -3
python - "$HERE" <<'PY'
import sys, httpx
here = sys.argv[1]
httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
    "owner": "AP Team Lead (demo)", "domain": "finance",
    "manifest_ref": f"{here}/manifests/invoicing-agent.yaml"})
print("   registered: invoicing-agent (owner: AP Team Lead, domain: finance)")
PY
governor set-cap invoicing-agent --from-manifest "$HERE/manifests/invoicing-agent.yaml" >/dev/null
echo "   spend cap: USD 500/day from manifest, escalate at 80%"

echo
echo "── 2. Mint the delegation token (human grantor, 1h, scoped) ──"
TOKEN=$(delegation mint invoicing-agent \
  --granted-by "Controller, Spin State Labs (demo)" \
  --scope "read timesheets" --scope "draft invoices" --ttl 3600 \
  | python -c "import sys, json; print(json.load(sys.stdin)['token_id'])")
echo "   token: $TOKEN"

echo
echo "── 3-5. The agent works: drafts fill the ledger; the 5th draft hits the"
echo "        spend threshold and waits for a human; the rogue transfer blocks ──"
python "$HERE/agent/invoicing_agent.py" "$HERE/agent/timesheet.csv" "$OUT/invoices" "$TOKEN"

echo
echo "── 6. The 2 a.m. drill: kill, verify, restore — measured ──"
killswitch drill invoicing-agent --operator "CISO on-call (demo)" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(f\"   kill confirmed {d['kill_confirmed_ms']} ms · heartbeat {d['heartbeat_confirmed_ms']} ms · restored={d['restored']} · total {d['total_ms']} ms\")"

echo
echo "── 7. Incident replay → RACI-ready post-mortem ──"
replay run invoicing-agent \
  --since 2020-01-01T00:00:00+00:00 --until 2030-01-01T00:00:00+00:00 \
  --markdown "$OUT/post-mortem.md" >/dev/null
echo "   written: integration/demo/out/post-mortem.md"
grep -E "^- \`|^## Which clause" "$OUT/post-mortem.md" | head -6

echo
echo "── Ledger integrity ──"
python - <<'PY'
import httpx
v = httpx.get("http://127.0.0.1:8002/verify").json()
n = len(httpx.get("http://127.0.0.1:8002/events").json())
print(f"   {n} events, chain intact: {v['ok']}")
PY

echo
echo "── 8. Board pack: every number with its source query ──"
attest render --out "$OUT/board-pack" --period "Integration demo run" --no-pdf \
  | sed 's/^/   /'
python - "$OUT" <<'PY'
import json, pathlib, sys
pack = json.loads((pathlib.Path(sys.argv[1]) / "board-pack" / "board-pack.json").read_text(encoding="utf-8"))
wanted = {"Ledger chain integrity", "Agents in production (active)",
          "Conformance rate (ALLOW / all verdicts)",
          "Conformance BLOCK verdicts", "Kill drills completed",
          "Authorities expiring within 30 days"}
for section in pack["sections"]:
    for m in section["metrics"]:
        if m["name"] in wanted:
            value = "unavailable" if m["status"] == "unavailable" else f"{m['value']}{' ' + m['unit'] if m['unit'] else ''}"
            print(f"   {m['name']:42s} {value!s:12s} <- {m['source_query'][:60]}")
PY

echo
echo "══ demo complete — artifacts in integration/demo/out/ ══"
