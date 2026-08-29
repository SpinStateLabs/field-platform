#!/usr/bin/env bash
# conformance-sentinel demo — <60s. Boots the full enforcement stack and
# walks one agent from ALLOW to every kind of refusal.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
export FIELD_DATA_DIR="$WORK" FIELD_MANIFEST_DIR="$WORK"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
# Sentinel defaults to safe log-only; this demo showcases enforcement,
# so opt in explicitly (S1 / ADR 02 safety ordering).
export FIELD_SENTINEL_MODE=enforce
sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_KILLSWITCH_URL=http://127.0.0.1:8005

python - "$WORK" <<'PY'
import sys, time, pathlib, yaml, httpx
from field_core.templates_api import template_data

for port in (8001, 8002, 8003, 8004, 8005, 8006):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)

work = pathlib.Path(sys.argv[1])
data = template_data("default")
data["agent"].update(name="invoicing-agent", description="drafts invoices")
data["identity"].update(principal="Controller, Spin State Labs",
                        org="Spin State Labs", jurisdiction=["PIPEDA"],
                        model_provider="Anthropic")
data["enforcement"]["kill_switch"].update(
    endpoint="http://127.0.0.1:8005/kill/invoicing-agent", method="HTTP POST")
data["enforcement"]["escalation_triggers"] = ["send invoice"]
data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500,
                                    "period": "daily", "on_breach": "halt"}
data["ledger"]["store"] = "sealed-ledger service"
data["delegation"].update(granted_by="Controller, Spin State Labs",
                          scope=["read timesheets", "draft invoices", "send invoice email"],
                          expiry="2027-06-30")
data["delegation"]["revocation"] = {"method": "HTTP POST",
                                    "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"}
manifest = work / "invoicing-agent.yaml"
manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
    "owner": "Controller, Spin State Labs", "domain": "finance",
    "manifest_ref": str(manifest)})
httpx.put("http://127.0.0.1:8006/caps/invoicing-agent", json={
    "agent_id": "invoicing-agent", "limit_cents": 50_000, "period": "daily",
    "escalate_at_pct": 80})
tok = httpx.post("http://127.0.0.1:8003/tokens", json={
    "agent_id": "invoicing-agent", "granted_by": "Controller, Spin State Labs",
    "scope": ["read timesheets", "draft invoices"], "ttl_seconds": 3600}).json()
print(tok["token_id"])
PY
TOKEN=$(python - "$WORK" <<'PY'
import sys, httpx
toks = httpx.get("http://127.0.0.1:8003/tokens").json()
print(toks[0]["token_id"])
PY
)

show() { python -c "import sys,json; d=json.load(sys.stdin); print(f\"  {d['decision']:8s} clause={d['clause_id']}  {'; '.join(d['reasons'])}\")"; }

echo "=== 1. In scope, token active, budget fine -> ALLOW ==="
sentinel check invoicing-agent "draft invoices" --token-id "$TOKEN" | show || true

echo
echo "=== 2. Out of scope ('transfer funds') -> BLOCK D.scope ==="
sentinel check invoicing-agent "transfer funds" --token-id "$TOKEN" | show || true

echo
echo "=== 3. No token -> BLOCK D.token ==="
sentinel check invoicing-agent "draft invoices" | show || true

echo
echo "=== 4. Kill the agent -> BLOCK E.kill_switch, instantly ==="
killswitch agent invoicing-agent --operator "CISO" --reason "demo" >/dev/null
sentinel check invoicing-agent "draft invoices" --token-id "$TOKEN" | show || true
killswitch revive invoicing-agent --operator "CISO" >/dev/null

echo
echo "=== 5. Spend to 82% -> ESCALATE E.spend_threshold ==="
governor spend invoicing-agent --cents 41000 >/dev/null
sentinel check invoicing-agent "draft invoices" --token-id "$TOKEN" | show || true

echo
echo "=== 6. The ledger recorded every verdict ==="
python - <<'PY'
import httpx
events = httpx.get("http://127.0.0.1:8002/events").json()
for e in events:
    if e["event_type"].startswith(("conformance.", "kill.", "delegation.")):
        clause = (e["payload"] or {}).get("clause_id", "")
        print(f"  {e['event_type']:22s} {clause or '':22s} agent={e['agent_id']}")
print("verify:", httpx.get("http://127.0.0.1:8002/verify").json()["ok"])
PY

echo
echo "demo complete."
