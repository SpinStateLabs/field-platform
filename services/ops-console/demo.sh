#!/usr/bin/env bash
# ops-console demo — boots the full stack + console with a lively fleet,
# then leaves it running for you to explore at http://127.0.0.1:8011/
# Ctrl-C to stop everything.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
HERE="$(cd "$(dirname "$0")" && pwd)"
export FIELD_DATA_DIR="$WORK" FIELD_MANIFEST_DIR="$WORK"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT INT

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004 FIELD_KILLSWITCH_URL=http://127.0.0.1:8005
console serve --port 8011 >/dev/null 2>&1 & PIDS+=($!)

python - "$WORK" <<'PY'
import sys, time, pathlib, yaml, httpx
from field_core.templates_api import template_data

for port in (8001, 8002, 8003, 8004, 8005, 8006, 8011):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)

work = pathlib.Path(sys.argv[1])
def manifest_for(name, scope):
    data = template_data("default")
    data["agent"].update(name=name, description=f"{name} (SYNTHETIC demo)")
    data["identity"].update(principal="Controller, Spin State Labs (demo)",
                            org="Spin State Labs", jurisdiction=["PIPEDA"],
                            model_provider="Anthropic")
    data["enforcement"]["kill_switch"].update(
        endpoint=f"http://127.0.0.1:8005/kill/{name}", method="HTTP POST")
    data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500,
                                        "period": "daily", "on_breach": "halt"}
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"].update(granted_by="Controller, Spin State Labs (demo)",
                              scope=scope, expiry="2027-06-30")
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"}
    path = work / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(path)

fleet = [
    ("invoicing-agent", "AP Team Lead", "finance",
     ["read timesheets", "draft invoices"]),
    ("forecast-agent", "FP&A Lead", "finance",
     ["read planning models", "draft forecasts"]),
    ("crm-enrich-agent", "RevOps Lead", "sales",
     ["read crm records", "draft enrichment notes"]),
]
for agent_id, owner, domain, scope in fleet:
    httpx.post("http://127.0.0.1:8001/agents", json={
        "agent_id": agent_id, "name": agent_id, "owner": owner,
        "domain": domain, "manifest_ref": manifest_for(agent_id, scope)})
    httpx.put(f"http://127.0.0.1:8006/caps/{agent_id}", json={
        "agent_id": agent_id, "limit_cents": 50_000, "period": "daily",
        "escalate_at_pct": 80})
    tok = httpx.post("http://127.0.0.1:8003/tokens", json={
        "agent_id": agent_id, "granted_by": "Controller, Spin State Labs (demo)",
        "scope": scope, "ttl_seconds": 7200}).json()
    # some governed activity so the ledger tail is alive
    httpx.post("http://127.0.0.1:8004/check", json={
        "agent_id": agent_id, "action": scope[0], "token_id": tok["token_id"]})

# one drama: invoicing spends to 82% and tries something rogue
httpx.post("http://127.0.0.1:8006/spend",
           json={"agent_id": "invoicing-agent", "cents": 41_000})
toks = httpx.get("http://127.0.0.1:8003/tokens",
                 params={"agent_id": "invoicing-agent"}).json()
httpx.post("http://127.0.0.1:8004/check", json={
    "agent_id": "invoicing-agent", "action": "transfer funds",
    "token_id": toks[0]["token_id"]})
print("fleet staged: 3 agents, 3 tokens, 1 escalation, 1 rogue BLOCK")
PY

echo
echo "══════════════════════════════════════════════════════"
echo "  FIELD Ops Console →  http://127.0.0.1:8011/"
echo "  3 governed agents · live ledger · try the harness"
echo "  Ctrl-C stops the whole stack."
echo "══════════════════════════════════════════════════════"
wait