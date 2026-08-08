#!/usr/bin/env bash
# agent-registry demo — <60s. Register, list, scan for shadow agents.
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

echo "=== 1. Register the governed invoicing agent ==="
registry add invoicing-agent \
  --name "Invoice Drafting Copilot" \
  --owner "Controller, Spin State Labs" \
  --domain finance \
  --manifest-ref manifests/invoicing-agent.yaml \
  --path "$DB" >/dev/null
registry list --path "$DB"

echo
echo "=== 2. Shadow-agent scan: n8n export + service-account CSV (synthetic) ==="
registry scan \
  --n8n "$HERE/tests/fixtures/n8n-export.json" \
  --accounts "$HERE/tests/fixtures/service-accounts.csv" \
  --path "$DB" || echo "(exit 3 — candidates found, review queue above)"

echo
echo "demo complete."
