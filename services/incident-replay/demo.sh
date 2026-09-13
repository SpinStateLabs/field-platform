#!/usr/bin/env bash
# incident-replay demo — <60s. Stages a governed incident, then replays it.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# The registered manifest (C3): Consulted/Informed are read from it. Synthetic
# demo values, shared with the integration demo.
MANIFEST="$(cd "$HERE/../../integration/demo/manifests" && pwd)/invoicing-agent.yaml"
[ -f "$MANIFEST" ] || { echo "demo manifest not found: $MANIFEST"; exit 1; }

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

registry serve --port 8001 >/dev/null 2>&1 & PIDS+=($!)
ledger serve --port 8002 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REGISTRY_URL=http://127.0.0.1:8001 FIELD_LEDGER_URL=http://127.0.0.1:8002
delegation serve --port 8003 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_DELEGATION_URL=http://127.0.0.1:8003
replay serve --port 8007 >/dev/null 2>&1 & PIDS+=($!)
export FIELD_REPLAY_URL=http://127.0.0.1:8007

python - "$MANIFEST" <<'PY'
import sys, time, httpx
manifest = sys.argv[1]
for port in (8001, 8002, 8003, 8007):
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5); break
        except Exception: time.sleep(0.25)

httpx.post("http://127.0.0.1:8001/agents", json={
    "agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
    "owner": "AP Team Lead", "domain": "finance", "manifest_ref": manifest})
httpx.post("http://127.0.0.1:8003/tokens", json={
    "agent_id": "invoicing-agent", "granted_by": "Controller, Spin State Labs",
    "scope": ["draft invoices"], "ttl_seconds": 86400})
for et, payload in (
    ("conformance.allow", {"action": "draft invoices"}),
    ("conformance.block", {"action": "transfer funds", "clause_id": "D.scope"}),
    ("kill.agent", {"operator": "CISO on-call", "reason": "scope probing"}),
):
    httpx.post("http://127.0.0.1:8002/events", json={
        "event_type": et, "agent_id": "invoicing-agent", "payload": payload})
print("incident staged: allow -> out-of-scope block -> kill")
PY

echo
echo "=== The RACI-ready post-mortem ==="
replay run invoicing-agent \
  --since 2020-01-01T00:00:00+00:00 --until 2030-01-01T00:00:00+00:00 \
  --markdown "$WORK/post-mortem.md"
cat "$WORK/post-mortem.md"

echo
echo "=== Where each RACI party came from (raci_sources) ==="
python - <<'PY'
import sys, httpx
pm = httpx.post("http://127.0.0.1:8007/replay", timeout=30.0, json={
    "agent_id": "invoicing-agent",
    "since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}).json()
for role, source in pm["raci_sources"].items():
    print(f"  {role:<12} {source}")
print(f"  manifest     resolved={pm['manifest_resolved']} ({pm['manifest_detail']})")
if not pm["manifest_resolved"]:
    sys.exit("the registered manifest_ref did not resolve")
PY

echo
echo "demo complete."
