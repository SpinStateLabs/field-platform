#!/usr/bin/env bash
# force-gateway demo — <60s. Phase F1: the gateway as the LLM-egress
# enforcement point. Boots the real spine locally (registry, ledger,
# delegation, governor, kill-switch, sentinel in ENFORCE), provisions a demo
# agent WITH a manifest, a cap and a token scoped to `llm.messages`, then runs
# the gateway with FORCE_GATEWAY_ENFORCE=1 on the mock upstream (no API key):
# no headers ⇒ 401; the governed call ⇒ 200; the agent is killed through the
# kill-switch; the next call ⇒ 403 E.kill_switch AT THE EGRESS, and
# `gateway.refused` is in the ledger. Every port is freed on exit (trap).
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
export FIELD_MANIFEST_DIR="$WORKW"
# Keyless, secretless, rosterless on purpose: never inherit an operator's.
unset FIELD_SHARED_SECRET FORCE_GATEWAY_URL ANTHROPIC_API_KEY FIELD_DOA_ROSTER \
      FIELD_KILL_ENDPOINT_ALLOWLIST FIELD_SENTINEL_JUDGE FORCE_HYGIENE_JUDGE \
      FORCE_GATEWAY_SENTINEL_TIMEOUT FORCE_GATEWAY_TOOL_CHECK || true
PIDS=()
# sleep 1: let the killed services release their sqlite files (Windows file locks)
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

# A stale stack on any of the demo's ports would be talked to as if it were
# ours: refuse loudly instead.
python - 8001 8002 8003 8004 8005 8006 8009 <<'PY'
import socket, sys
busy = []
for port in map(int, sys.argv[1:]):
    s = socket.socket()
    s.settimeout(0.2)
    if s.connect_ex(("127.0.0.1", port)) == 0:
        busy.append(port)
    s.close()
if busy:
    sys.exit(f"ports already listening: {busy} — stop the stale stack first")
PY

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
governor serve --port 8006 >/dev/null 2>&1 & PIDS+=($!)
killswitch serve --port 8005 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003 FIELD_GOVERNOR_URL=http://127.0.0.1:8006
export FIELD_KILLSWITCH_URL=http://127.0.0.1:8005
# The sentinel is safe log-only by default; the demo shows enforcement.
FIELD_SENTINEL_MODE=enforce sentinel serve --port 8004 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_SENTINEL_URL=http://127.0.0.1:8004

wait_health() {
  python - "$@" <<'PY'
import sys, time, httpx
for url in sys.argv[1:]:
    for _ in range(120):
        try:
            if httpx.get(url + "/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    else:
        sys.exit("never answered: " + url)
PY
}
wait_health http://127.0.0.1:8001 http://127.0.0.1:8002 http://127.0.0.1:8003 \
            http://127.0.0.1:8004 http://127.0.0.1:8005 http://127.0.0.1:8006

echo "=== 1. Provision demo-agent: manifest on disk, registered by ref, capped, tokened for llm.messages ==="
python - "$WORKW" <<'PY'
import pathlib, sys, yaml, httpx
from field_core.templates_api import template_data
work = pathlib.Path(sys.argv[1])
data = template_data("default")
data["agent"]["name"] = "demo-agent"
data["agent"]["description"] = "Demo agent: calls the model through the enforcing gateway"
data["identity"].update(principal="Controller, Spin State Labs", org="Spin State Labs",
                        jurisdiction=["PIPEDA"], model_provider="Anthropic")
data["enforcement"]["kill_switch"].update(endpoint="http://127.0.0.1:8005/kill/demo-agent", method="HTTP POST")
data["enforcement"]["escalation_triggers"] = []
data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500, "period": "daily", "on_breach": "halt"}
data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
data["delegation"].update(granted_by="Controller, Spin State Labs",
                          scope=["read timesheets", "llm.messages"], expiry="2027-06-30",
                          revocation={"method": "HTTP POST", "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"})
manifest = work / "demo-agent.yaml"
manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
r = httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "demo-agent", "name": "Demo agent", "owner": "Controller, Spin State Labs",
    "domain": "demo", "manifest_ref": str(manifest)}, timeout=10.0)
r.raise_for_status()
r = httpx.put("http://127.0.0.1:8006/caps/demo-agent", json={
    "agent_id": "demo-agent", "limit_cents": 50_000, "period": "daily", "escalate_at_pct": 80}, timeout=10.0)
r.raise_for_status()
r = httpx.post("http://127.0.0.1:8003/tokens", json={
    "agent_id": "demo-agent", "granted_by": "Controller, Spin State Labs",
    "scope": ["read timesheets", "llm.messages"], "ttl_seconds": 3600}, timeout=10.0)
r.raise_for_status()
(work / "token").write_text(r.json()["token_id"], encoding="ascii")
print("registered demo-agent (manifest_ref -> the file above), cap USD 500/daily, token scope",
      r.json()["scope"], "(token id kept in a file, not printed)")
PY
TOKEN="$(cat "$WORK/token")"

echo
echo "=== 2. The gateway, ENFORCING, on the mock upstream (FORCE_GATEWAY_ENFORCE=1) ==="
# The compose stack no longer passes the CLI mock flag (D2): the env var is the switch.
FORCE_GATEWAY_ENFORCE=1 FORCE_GATEWAY_MOCK=1 forcegw serve --port 8009 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_GATEWAY_URL=http://127.0.0.1:8009
python - <<'PY'
import sys, time, httpx
for _ in range(120):
    try:
        h = httpx.get("http://127.0.0.1:8009/health", timeout=0.5).json()
        if h.get("service") == "force-gateway":
            assert h["mock"] is True and h["enforce"] is True and h["sentinel_url"], h
            print("health:", {k: h[k] for k in ("mock", "enforce", "tool_check", "sentinel_url", "sentinel_timeout_seconds")})
            sys.exit(0)
    except (httpx.HTTPError, ValueError):
        pass
    time.sleep(0.25)
sys.exit("force-gateway never answered")
PY

MSG='{"model":"claude-x","max_tokens":64,"system":"You are the demo agent.","messages":[{"role":"user","content":"Draft the invoice."}]}'

echo
echo "=== 3. No identity headers ⇒ 401 (never forwarded) ==="
python - "$MSG" <<'PY'
import json, sys, httpx
r = httpx.post("http://127.0.0.1:8009/v1/messages", json=json.loads(sys.argv[1]), timeout=10.0)
print(r.status_code, r.json()["detail"])
assert r.status_code == 401, r.text
PY

echo
echo "=== 4. x-field-agent-id + x-field-token ⇒ sentinel ALLOW ⇒ 200 (mock model, FORCE-injected, metered) ==="
python - "$MSG" "$TOKEN" <<'PY'
import json, sys, httpx
r = httpx.post("http://127.0.0.1:8009/v1/messages", json=json.loads(sys.argv[1]),
               headers={"x-field-agent-id": "demo-agent", "x-field-token": sys.argv[2]}, timeout=30.0)
assert r.status_code == 200, r.text
body = r.json()
print("model:", body["model"], "| usage:", body["usage"])
allows = httpx.get("http://127.0.0.1:8002/events", params={"event_type": "conformance.allow"}, timeout=10.0).json()
print("sentinel ledgered:", [(e["agent_id"], e["payload"]["action"]) for e in allows])
usage = httpx.get("http://127.0.0.1:8006/usage/demo-agent", timeout=10.0).json()
print("governor usage for demo-agent:", usage["total_input_tokens"], "in /", usage["total_output_tokens"], "out")
assert usage["total_input_tokens"] == 240 and usage["total_output_tokens"] == 118, usage
PY

echo
echo "=== 5. Kill demo-agent through the kill-switch ==="
python - <<'PY'
import httpx
r = httpx.post("http://127.0.0.1:8005/kill/demo-agent", json={"operator": "Don Hagell", "reason": "F1 demo"}, timeout=10.0)
r.raise_for_status()
k = r.json()
print("kill-switch:", {"previous_status": k["previous_status"], "status": k["status"]})
status = httpx.get("http://127.0.0.1:8001/agents/demo-agent", timeout=10.0).json()["status"]
assert status == "killed", status
PY

echo
echo "=== 6. The same headers ⇒ 403 E.kill_switch AT THE EGRESS (no upstream call) ==="
python - "$MSG" "$TOKEN" <<'PY'
import json, sys, httpx
r = httpx.post("http://127.0.0.1:8009/v1/messages", json=json.loads(sys.argv[1]),
               headers={"x-field-agent-id": "demo-agent", "x-field-token": sys.argv[2]}, timeout=30.0)
print(r.status_code, r.json())
assert r.status_code == 403 and r.json()["clause_id"] == "E.kill_switch", r.text
PY

echo
echo "=== 7. gateway.refused in the ledger; the allowed call is the only instrumented one ==="
python - <<'PY'
import httpx
refused = httpx.get("http://127.0.0.1:8002/events", params={"event_type": "gateway.refused"}, timeout=10.0).json()
print("gateway.refused events:", len(refused), [e["payload"] for e in refused])
assert len(refused) >= 1 and refused[-1]["payload"]["clause_id"] == "E.kill_switch"
assert refused[-1]["agent_id"] == "force-gateway"  # the gateway signs its own events
t = httpx.get("http://127.0.0.1:8009/telemetry", timeout=10.0).json()
print("telemetry total_requests:", t["total_requests"], "(the refused call was never instrumented)")
assert t["total_requests"] == 1, t
assert httpx.get("http://127.0.0.1:8002/verify", timeout=10.0).json()["ok"]
print("ledger chain verifies: ok")
PY

echo
echo "demo complete."
