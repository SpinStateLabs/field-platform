#!/usr/bin/env bash
# field-agent demo — <60s. Boots the six governance services, then puts a
# tiny agent under governance THROUGH THE SDK: governed ALLOW, priced usage,
# rogue-model finding, out-of-scope BLOCK, kill ⇒ AgentKilled halt.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"
# Inline python heredocs have no CLI reconfigure loop — force UTF-8 stdout
# for every Python child (Windows consoles default to cp1252).
export PYTHONUTF8=1

WORK="$(mktemp -d)"
# Windows Python can't see MSYS /tmp paths — hand every Python process the
# native form so bash and the services share one physical directory.
WORKW="$(cygpath -w "$WORK" 2>/dev/null || echo "$WORK")"
export FIELD_DATA_DIR="$WORKW"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

AGENT=sdk-demo-agent

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
# The served sentinel defaults to safe log-only; this demo showcases
# enforcement, so opt in explicitly (S1 / ADR 02 safety ordering).
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
echo "=== 1. Operator setup: manifest → register → cap → policy → mint ==="
python - <<PY
import yaml
from field_core.templates_api import template_data
data = template_data("default")
data["agent"]["name"] = "$AGENT"
data["agent"]["description"] = "SDK demo: governed draft loop"
data["identity"]["principal"] = "Controller, Spin State Labs"
data["identity"]["org"] = "Spin State Labs"
data["identity"]["jurisdiction"] = ["PIPEDA"]
data["identity"]["model_provider"] = "Anthropic"
data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/$AGENT"
data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
data["enforcement"]["escalation_triggers"] = ["wire transfer"]
data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500,
                                    "period": "daily", "on_breach": "halt"}
data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
data["delegation"]["granted_by"] = "Controller, Spin State Labs"
data["delegation"]["scope"] = ["read timesheets", "draft invoices"]
data["delegation"]["expiry"] = "2027-06-30"
data["delegation"]["revocation"] = {"method": "HTTP POST",
    "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"}
import os
os.makedirs(r"$WORKW", exist_ok=True)
open(r"$WORKW/$AGENT.yaml", "w", encoding="utf-8").write(
    yaml.safe_dump(data, sort_keys=False))
from field_agent import bootstrap
rec = bootstrap.register("$AGENT", name="SDK Demo Agent",
                         owner="Controller, Spin State Labs (demo)",
                         domain="finance", manifest_ref=r"$WORKW/$AGENT.yaml")
print(f"   registered: {rec['agent_id']} status={rec['status']}")
PY
field validate "$WORKW/$AGENT.yaml" >/dev/null && echo "   manifest valid"
governor set-cap "$AGENT" --from-manifest "$WORKW/$AGENT.yaml" >/dev/null && echo "   cap set from manifest (\$500/day)"
governor set-policy "$AGENT" --allowed-model claude-haiku-4-5 --token-rate-limit 200000 >/dev/null && echo "   usage policy: haiku only, 200k tokens/h"
TOKEN=$(fieldagent mint "$AGENT" --granted-by "Controller, Spin State Labs (demo)" \
  --scope "read timesheets" --scope "draft invoices" --ttl-seconds 3600 \
  | python -c "import sys,json;print(json.load(sys.stdin)['token_id'])")
echo "   delegation token minted: ${TOKEN:0:8}…"

echo
echo "=== 2. Hook 1+3 — governed action runs only on ALLOW, after ensure_alive ==="
python - <<PY
from field_agent import FieldAgent
agent = FieldAgent("$AGENT", token_id="$TOKEN")

@agent.governed("draft invoices")
def draft(n):
    print(f"   drafted INV-{n:03d} (body ran only because the sentinel said ALLOW)")

agent.ensure_alive()
print("   heartbeat: alive")
draft(1)
PY

echo
echo "=== 3. Hook 2 — usage reported, priced from the dated price book ==="
python - <<PY
from field_agent import FieldAgent
report = FieldAgent("$AGENT").report_usage(
    "haiku-4.5", input_tokens=42_000, output_tokens=9_000, note="demo draft")
r = report.record
print(f"   {r.model}: {r.input_tokens}+{r.output_tokens} tokens "
      f"→ {r.cost_units} units ({report.status.token_cost_display}), findings: {len(report.rogue)}")
PY

echo
echo "=== 4. Rogue model — Opus off the Haiku allow-list is flagged ==="
fieldagent report-usage "$AGENT" --model claude-opus-4-8 --input-tokens 12000 --output-tokens 3000 >/dev/null \
  || echo "   (exit 3 — rogue_model finding + escalation + ledger event, as designed)"

echo
echo "=== 5. Out-of-scope action — BLOCK before it runs ==="
fieldagent check "$AGENT" "transfer funds" --token-id "$TOKEN" >/dev/null \
  || echo "   (exit 1 — BLOCK D.scope, as designed)"

echo
echo "=== 6. Kill ⇒ the SDK halts the agent ==="
killswitch agent "$AGENT" --operator "CISO on-call (demo)" --reason "demo halt" >/dev/null && echo "   killed via kill-switch"
python - <<PY
from field_agent import FieldAgent, AgentKilled
try:
    FieldAgent("$AGENT").ensure_alive()
    print("   !! still alive — this must never print")
    raise SystemExit(2)
except AgentKilled as exc:
    print(f"   AgentKilled raised as designed: {exc}")
PY

echo
echo "=== 7. The ledger saw everything ==="
python - <<'PY'
import httpx
from field_core.authn import auth_headers  # bare clients 401 in secret estates
events = httpx.get("http://127.0.0.1:8002/events", headers=auth_headers()).json()
for e in events:
    print(f"   {e['event_type']:24s} agent={e['agent_id']}")
ok = httpx.get("http://127.0.0.1:8002/verify", headers=auth_headers()).json()["ok"]
print(f"   chain intact: {ok}")
PY

echo
echo "demo complete."
