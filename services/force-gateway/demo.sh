#!/usr/bin/env bash
# force-gateway demo — <60s. Mock upstream (no API key), FORCE injection,
# hygiene telemetry with rates, platform passthrough, and telemetry that
# survives a gateway restart (v1.2 D2).
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
# native form so bash and the gateway share one physical directory.
WORKW="$(cygpath -w "$WORK" 2>/dev/null || echo "$WORK")"
export FIELD_DATA_DIR="$WORKW"
# The demo is keyless and secretless on purpose: never inherit an operator's.
unset FIELD_SHARED_SECRET FORCE_GATEWAY_URL ANTHROPIC_API_KEY FIELD_GOVERNOR_URL FIELD_LEDGER_URL || true
PIDS=()
# sleep 1: let the killed gateway release telemetry.sqlite3 (Windows file locks)
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done; sleep 1; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

wait_health() {
  python - "$1" <<'PY'
import sys, time, httpx
url = sys.argv[1]
for _ in range(80):
    try:
        h = httpx.get(url + "/health", timeout=0.5).json()
        if h.get("service") == "force-gateway":
            assert h["mock"] is True and h["telemetry_store"] == "ok", h
            sys.exit(0)
    except (httpx.HTTPError, ValueError):
        pass
    time.sleep(0.25)
sys.exit("force-gateway never answered at " + url)
PY
}

# The compose stack no longer passes the CLI mock flag (D2): the env var is the switch.
FORCE_GATEWAY_MOCK=1 forcegw serve --port 8009 >/dev/null 2>&1 & PIDS+=($!)
GW_PID=$!
export FIELD_GATEWAY_URL=http://127.0.0.1:8009
wait_health "$FIELD_GATEWAY_URL"

echo "=== 1. The four presets (composed verbatim from the shipped protocol) ==="
forcegw presets

echo
echo "=== 2. First lines of the audit preset block ==="
forcegw presets --show audit | head -8

echo
echo "=== 3. A proxied call (mock upstream — no key, deterministic) ==="
python - <<'PY'
import httpx
r = httpx.post("http://127.0.0.1:8009/v1/messages",
    json={"model": "claude-x", "max_tokens": 512,
          "system": "You are the invoicing agent.",
          "messages": [{"role": "user", "content": "Draft the invoice."}]},
    headers={"x-force-preset": "audit", "x-field-agent-id": "invoicing-agent"},
    timeout=10.0)
r.raise_for_status()
body = r.json()
print("model:", body["model"])
print("--- response text ---")
print(body["content"][0]["text"][:400])
PY

echo
echo "=== 4. Platform judge traffic: x-force-passthrough: judge (forwarded untouched, not hygiene telemetry) ==="
python - <<'PY'
import httpx
r = httpx.post("http://127.0.0.1:8009/v1/messages",
    json={"model": "claude-x", "max_tokens": 64, "system": "judge rubric",
          "messages": [{"role": "user", "content": "score this"}]},
    headers={"x-force-passthrough": "judge"}, timeout=10.0)
r.raise_for_status()
print("passthrough status:", r.status_code)
PY

echo
echo "=== 5. Hygiene telemetry (labeled heuristic): counts, rates, coverage ==="
python - <<'PY'
import httpx
t = httpx.get("http://127.0.0.1:8009/telemetry", timeout=10.0).json()
print("method        :", t["method"])
print("total_requests:", t["total_requests"], " by_preset:", t["by_preset"])
for route, windows in t["rates"].items():
    for window, r in windows.items():
        print(f"rates[{route}][{window}] requests={r['requests']} "
              f"confidence_tag={r['confidence_tag_rate']} flattery_free={r['flattery_free_rate']} "
              f"cot={r['cot_structure_rate']}")
cov = t["coverage"]
print("coverage      : instrumented", cov["instrumented"], "passthrough", cov["passthrough"],
      "bypassed", cov["bypassed"])
assert t["total_requests"] == 1 and cov["passthrough"] == 1, t
PY

echo
echo "=== 6. Restart: a new gateway process on the same FIELD_DATA_DIR resumes the telemetry ==="
kill "$GW_PID" 2>/dev/null || true
FORCE_GATEWAY_MOCK=1 forcegw serve --port 8019 >/dev/null 2>&1 & PIDS+=($!)
wait_health http://127.0.0.1:8019
python - <<'PY'
import httpx
t = httpx.get("http://127.0.0.1:8019/telemetry", timeout=10.0).json()
print("after restart : total_requests", t["total_requests"], " passthrough",
      t["coverage"]["passthrough"], " recent[0].preset", t["recent"][0]["preset"])
assert t["total_requests"] == 1 and t["coverage"]["passthrough"] == 1, t
PY

echo
echo "demo complete."
