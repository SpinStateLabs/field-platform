#!/usr/bin/env bash
# compliance-crosswalk demo — <60s. Offline coverage of the financial-agent
# template: declared vs. evidenced, citations source-grounded or explicitly
# pending; then the regwatch source inventory (no network: no --fetch).
set -euo pipefail

VENVBIN=""
for candidate in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  [ -x "$candidate/python.exe" ] || [ -x "$candidate/python" ] && VENVBIN="$candidate"
done
[ -n "$VENVBIN" ] || { echo "field-platform venv not found"; exit 1; }
PATH="$VENVBIN:$PATH"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "=== 1. Frameworks in scope (cited / pending-text / pending-purchase) ==="
crosswalk frameworks

echo
echo "=== 2. Coverage of the raw financial-agent template (placeholders = gaps) ==="
field templates --show financial-agent --out "$WORK/fin.yaml"
crosswalk run "$WORK/fin.yaml" --markdown "$WORK/report.md" || true
grep -E "^\*Coverage|Citation status" "$WORK/report.md" | head -4

echo
echo "=== 3. The declared-vs-evidenced matrix ==="
sed -n '/| Control | L |/,/^$/p' "$WORK/report.md"

echo
echo "=== 4. regwatch: the watched sources (inventory only — no fetch, exit 0) ==="
FIELD_DATA_DIR="$WORK" crosswalk regwatch check 2>&1 | grep -E '"(framework|via|url|status|reason)"'

echo
echo "demo complete."
