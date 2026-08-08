#!/usr/bin/env bash
# force-gateway demo — <60s. Mock upstream (no API key), FORCE injection,
# hygiene telemetry.
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

forcegw serve --port 8009 --mock >/dev/null 2>&1 & PIDS+=($!)
export FIELD_GATEWAY_URL=http://127.0.0.1:8009
python - <<'PY'
import time, httpx
for _ in range(60):
    try:
        httpx.get("http://127.0.0.1:8009/health", timeout=0.5); break
    except Exception: time.sleep(0.25)
PY

echo "=== 1. The four presets (composed verbatim from the shipped protocol) ==="
forcegw presets

echo
echo "=== 2. First lines of the audit preset block ==="
forcegw presets --show audit | head -8

echo
echo "=== 3. A proxied call (mock upstream — no key, deterministic) ==="
python - <<'PY'
import httpx, json
r = httpx.post("http://127.0.0.1:8009/v1/messages",
    json={"model": "claude-x", "max_tokens": 512,
          "system": "You are the invoicing agent.",
          "messages": [{"role": "user", "content": "Draft the invoice."}]},
    headers={"x-force-preset": "audit", "x-field-agent-id": "invoicing-agent"},
    timeout=10.0)
body = r.json()
print("model:", body["model"])
print("--- response text ---")
print(body["content"][0]["text"][:400])
PY

echo
echo "=== 4. Hygiene telemetry (labeled heuristic) ==="
forcegw telemetry | python -m json.tool | head -25

echo
echo "demo complete."
