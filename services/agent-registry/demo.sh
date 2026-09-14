#!/usr/bin/env bash
# agent-registry demo — <60s. Register (a manifest_ref must resolve), list,
# scan for shadow agents, unowned API keys and credential-shaped strings.
set -euo pipefail

if ! command -v registry >/dev/null 2>&1; then
  for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
    [ -x "$candidate/registry" ] || [ -x "$candidate/registry.exe" ] && PATH="$candidate:$PATH"
  done
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DB="$WORK/agents.sqlite3"
# A relative manifest_ref resolves under FIELD_MANIFEST_DIR (v1.2 D3b): point
# it at the suite's fixtures, where manifests/invoicing-agent.yaml is VALID.
FIELD_MANIFEST_DIR="$(cygpath -w "$HERE/tests/fixtures" 2>/dev/null || echo "$HERE/tests/fixtures")"
export FIELD_MANIFEST_DIR

echo "=== 1. Register the governed invoicing agent ==="
registry add invoicing-agent \
  --name "Invoice Drafting Copilot" \
  --owner "Controller, Spin State Labs" \
  --domain finance \
  --manifest-ref manifests/invoicing-agent.yaml \
  --path "$DB" >/dev/null
registry list --path "$DB"

echo
echo "=== 1b. A manifest_ref that does not resolve is refused (exit 2, nothing written) ==="
set +e
registry add ghost-agent --name "Ghost" --owner "Nobody" \
  --manifest-ref manifests/not-installed.yaml --path "$DB"
rc=$?
set -e
[ "$rc" -eq 2 ] || { echo "expected exit 2, got $rc"; exit 1; }
if registry list --path "$DB" | grep -q ghost-agent; then
  echo "ghost-agent was written despite the refusal"; exit 1
fi
echo "(exit 2 — refused, ghost-agent not registered)"

echo
echo "=== 2. Shadow-agent scan: n8n export + service-account CSV (synthetic) ==="
registry scan \
  --n8n "$HERE/tests/fixtures/n8n-export.json" \
  --accounts "$HERE/tests/fixtures/service-accounts.csv" \
  --path "$DB" || echo "(exit 3 — candidates found, review queue above)"

echo
echo "=== 3. API-key inventory (synthetic): owner / unowned / unknown-principal rules ==="
set +e
registry scan --api-keys "$HERE/tests/fixtures/api-keys.csv" --path "$DB" > "$WORK/keys.json"
rc=$?
set -e
[ "$rc" -eq 3 ] || { echo "expected exit 3, got $rc"; exit 1; }
PYTHONIOENCODING=utf-8 python - "$WORK/keys.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
for c in report["candidates"]:
    print(f"   {c['identifier'][:48]:48s} {c['reason']}")
PY
if grep -q "SYNTHETIC-DO-NOT-USE" "$WORK/keys.json"; then
  echo "a raw key value reached the report"; exit 1
fi
echo "(exit 3 — invoicing-agent-prod surfaced by owner although invoicing-agent is registered;"
echo " the key pasted as a key_name is redacted)"

echo
echo "=== 4. Secrets-text scan (synthetic values, assembled here; reported redacted) ==="
{
  printf 'ANTHROPIC_API_KEY=%s%s\n' "sk-" "ant-api03-SYNTHETICSYNTHETICSYNTHETICSYNTHETIC"
  printf 'aws_access_key_id = %s%s\n' "AK" "IASYNTHETIC0000000"
  printf 'task-runner-automation-agent-01 is an ordinary name\n'
} > "$WORK/dump.txt"
set +e
registry scan --secrets-text "$WORK/dump.txt" --path "$DB" > "$WORK/secrets.json"
rc=$?
set -e
[ "$rc" -eq 3 ] || { echo "expected exit 3, got $rc"; exit 1; }
PYTHONIOENCODING=utf-8 python - "$WORK/secrets.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
for h in report["secret_hits"]:
    print(f"   line {h['line']}: {h['pattern']:18s} breadth={h['breadth']:9s} {h['redacted']}  {h['fingerprint']}")
PY
if grep -q "SYNTHETICSYNTHETIC" "$WORK/secrets.json"; then
  echo "a raw secret reached the report"; exit 1
fi
echo "(exit 3 — 2 hits, both redacted; the ordinary name is not a hit)"

echo
echo "demo complete."
