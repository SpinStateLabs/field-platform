#!/usr/bin/env bash
# federation-broker demo — <60s. Two local orgs, one governed crossing.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
export FIELD_DATA_DIR="$WORK" FIELD_ORG_NAME="Spin State Labs"
PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_LEDGER_URL=http://127.0.0.1:8002
fedbroker serve --port 8010 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_FEDERATION_URL=http://127.0.0.1:8010

python - "$WORK" <<'PY'
import sys, time, pathlib, yaml, httpx
from field_core.templates_api import template_data

for port in (8002, 8010):
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)

# Org B (Borealis) prepares its agent's manifest, naming Org A as a peer.
data = template_data("client-facing-agent")
data["agent"]["name"] = "borealis-billing-agent"
data["identity"].update(principal="VP Finance, Borealis (demo)",
                        org="Borealis Example Corp", jurisdiction=["PIPEDA"],
                        model_provider="Anthropic")
data["enforcement"]["kill_switch"].update(endpoint="https://borealis.example/kill",
                                          method="HTTP POST")
data["ledger"]["store"] = "borealis WORM store (demo)"
data["delegation"].update(granted_by="VP Finance, Borealis (demo)",
                          scope=["exchange invoice status"])
data["delegation"]["revocation"] = {"method": "HTTP POST",
                                    "endpoint": "https://borealis.example/revoke"}
data["federated"] = {"isolated": False,
    "allowed_peers": [{"agent_id": "invoicing-agent", "org": "Spin State Labs",
                       "trust_basis": "federation contract FED-2026-001 (demo)"}],
    "contracts": [{"peer": "invoicing-agent", "contract_ref": "FED-2026-001",
                   "scope": "exchange invoice status"}]}
manifest = pathlib.Path(sys.argv[1]) / "borealis-agent.yaml"
manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
print("counterparty manifest written")

# Org A (Spin State) prepares OUR agent's manifest, naming Borealis as a peer.
import copy
ours = copy.deepcopy(data)
ours["agent"]["name"] = "invoicing-agent"
ours["identity"].update(principal="Controller, Spin State Labs (demo)",
                        org="Spin State Labs")
ours["enforcement"]["kill_switch"]["endpoint"] = "https://spinstate.example/kill"
ours["ledger"]["store"] = "sealed-ledger (demo)"
ours["delegation"]["granted_by"] = "Controller, Spin State Labs (demo)"
ours["delegation"]["revocation"] = {"method": "HTTP POST",
                                    "endpoint": "https://spinstate.example/revoke"}
ours["federated"] = {"isolated": False,
    "allowed_peers": [{"agent_id": "borealis-billing-agent",
                       "org": "Borealis Example Corp",
                       "trust_basis": "federation contract FED-2026-001 (demo)"}],
    "contracts": [{"peer": "borealis-billing-agent", "contract_ref": "FED-2026-001",
                   "scope": "exchange invoice status"}]}
(pathlib.Path(sys.argv[1]) / "our-agent.yaml").write_text(
    yaml.safe_dump(ours, sort_keys=False), encoding="utf-8")
print("our manifest written")
PY

echo
echo "=== 1. GC registers the federation contract ==="
fedbroker add-contract FED-2026-001 --org "Borealis Example Corp" \
  --scope "exchange invoice status" --data-class "invoice metadata" \
  --ref "gc-vault/FED-2026-001 (demo)" >/dev/null
fedbroker contracts | python -m json.tool

show() { python -c "import sys,json; d=json.load(sys.stdin); print(f\"  {d['decision']:8s} clause={d['clause_id']}  {'; '.join(d['reasons'])[:100]}\")"; }

echo
echo "=== 2. In-contract crossing -> ALLOW ==="
fedbroker crossing --org "Borealis Example Corp" --agent-id borealis-billing-agent \
  --manifest "$WORK/borealis-agent.yaml" \
  --scope "exchange invoice status" --data-class "invoice metadata" | show || true

echo
echo "=== 3. Same peer over-reaches: asks for customer PII -> BLOCK F.peer ==="
fedbroker crossing --org "Borealis Example Corp" --agent-id borealis-billing-agent \
  --manifest "$WORK/borealis-agent.yaml" \
  --scope "exchange invoice status" --data-class "customer PII" | show || true

echo
echo "=== 4. OUR invoicing-agent asks OUTBOUND under the same contract -> ALLOW ==="
# No `|| true` here: a refused request (exit 1) or a non-ALLOW verdict fails the demo.
fedbroker crossing --direction outbound --org "Borealis Example Corp"   --agent-id invoicing-agent --manifest "$WORK/our-agent.yaml"   --scope "exchange invoice status" --data-class "invoice metadata" > "$WORK/outbound.json"
python - "$WORK/outbound.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["decision"] == "ALLOW" and d["context"]["direction"] == "outbound", d
print(f"  {d['decision']:8s} direction={d['context']['direction']}  agent_id={d['agent_id']}")
PY

echo
echo "=== 5. Every crossing is a ledger event, with its direction ==="
python - <<'PY'
import httpx
for e in httpx.get("http://127.0.0.1:8002/events").json():
    p = e["payload"]
    print(f"  {e['event_type']:18s} {p.get('direction', ''):9s} {p.get('data_class', ''):18s} clause={p.get('clause_id')}")
print("verify:", httpx.get("http://127.0.0.1:8002/verify").json()["ok"])
PY

echo
echo "demo complete."
