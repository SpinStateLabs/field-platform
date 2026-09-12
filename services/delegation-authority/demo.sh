#!/usr/bin/env bash
# delegation-authority demo — <60s. Boots the spine (registry + ledger +
# delegation) on local ports, mints, introspects, revokes, and shows the
# ledger trail. Requires the field-platform venv.
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

echo "=== 0a. Write the agent manifest and the DOA roster ==="
# The roster must exist BEFORE the service starts: `delegation serve` reads
# FIELD_DOA_ROSTER from its own environment, so exporting it later would not
# reach the already-running process.
python - "$WORK" <<'PY'
import sys, pathlib, yaml
from field_core.templates_api import template_data

work = pathlib.Path(sys.argv[1])
data = template_data("default")
data["agent"]["name"] = "invoicing-agent"
data["identity"]["principal"] = "Controller, Spin State Labs"
data["delegation"]["granted_by"] = "Controller, Spin State Labs"
data["delegation"]["scope"] = ["read timesheets", "draft invoices"]
data["delegation"]["expiry"] = "2027-06-30"
(work / "invoicing-agent.yaml").write_text(
    yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

(work / "doa-roster.yaml").write_text(yaml.safe_dump({"grantors": [{
    "grantor": "Controller, Spin State Labs",
    "allowed_scope": ["read timesheets", "draft invoices"],
    "max_ttl_days": 30,
    "max_spend_usd": 500.0,
    "active": True,
}]}, sort_keys=False), encoding="utf-8")
print("manifest + roster written")
PY
export FIELD_DOA_ROSTER="$WORK/doa-roster.yaml"

echo
echo "=== 0b. Boot the spine (registry :8001, ledger :8002, delegation :8003) ==="
registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003

python - <<'PY'
import time, httpx
for port in (8001, 8002, 8003):
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)
PY

echo
echo "=== 1. Register the agent (WITH a manifest_ref — the roster needs it) ==="
python - "$WORK" <<'PY'
import sys, httpx
r = httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
    "owner": "Controller, Spin State Labs", "domain": "finance",
    "manifest_ref": f"{sys.argv[1]}/invoicing-agent.yaml"})
print("registered:", r.status_code)
PY

echo
echo "=== 1b. The DOA roster refuses a grantor who is not on it ==="
delegation mint invoicing-agent \
  --granted-by "Somebody Else, Nowhere Inc" \
  --scope "read timesheets" --ttl 3600 \
  && echo "UNEXPECTED: off-roster mint succeeded" \
  || echo "(exit 1 — 403 D.grantor: off-roster grantors cannot delegate)"

echo
echo "=== 2. Mint a 1-hour token as a rostered grantor, introspect it ==="
TOKEN_ID=$(delegation mint invoicing-agent \
  --granted-by "Controller, Spin State Labs" \
  --scope "read timesheets" --scope "draft invoices" --ttl 3600 \
  | python -c "import sys, json; print(json.load(sys.stdin)['token_id'])")
echo "token: $TOKEN_ID"
delegation introspect "$TOKEN_ID" | python -m json.tool

echo
echo "=== 2b. OAuth-style introspection (RFC 7662 shape) ==="
delegation oauth-introspect "$TOKEN_ID" | python -m json.tool

echo
echo "=== 3. Revoke it — introspection must now fail ==="
delegation revoke "$TOKEN_ID" >/dev/null
delegation introspect "$TOKEN_ID" | python -m json.tool || echo "(exit 1 — revoked token is dead)"
echo "   and the OAuth view says only {\"active\": false} — never why:"
delegation oauth-introspect "$TOKEN_ID" | python -m json.tool || true

echo
echo "=== 4. The ledger saw everything ==="
python - <<'PY'
import httpx
for e in httpx.get("http://127.0.0.1:8002/events").json():
    print(f"  {e['event_type']:20s} agent={e['agent_id']} hash={e['hash'][:12]}…")
print("verify:", httpx.get("http://127.0.0.1:8002/verify").json())
PY

echo
echo "demo complete."
