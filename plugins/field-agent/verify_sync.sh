#!/usr/bin/env bash
# Drift check: plugin templates must be byte-identical to their monorepo
# sources (mapping in templates/SOURCES.md). Run from the repo root.
# Exit 0 = in sync; exit 1 = drift (re-vendor + update SOURCES.md stamp).
set -uo pipefail

PLUGIN=plugins/field-agent/templates
declare -A MAP=(
  ["$PLUGIN/agent_template.py"]="packages/field-agent/examples/agent_template.py"
  ["$PLUGIN/bootstrap_operator.py"]="packages/field-agent/examples/04_bootstrap_operator.py"
  ["$PLUGIN/rest_api.sh"]="packages/field-agent/examples/05_rest_api.sh"
  ["$PLUGIN/field-manifest-default.yaml"]="packages/field-core/src/field_core/templates/field-manifest-default.yaml"
  ["$PLUGIN/manifest-schema.json"]="packages/field-core/src/field_core/schema/manifest-schema.json"
  ["$PLUGIN/example-manifest-invoicing-agent.yaml"]="integration/demo/manifests/invoicing-agent.yaml"
)

fail=0
for vendored in "${!MAP[@]}"; do
  src="${MAP[$vendored]}"
  if [ ! -f "$src" ]; then
    echo "MISSING SOURCE: $src (moved? update SOURCES.md + this script)"
    fail=1
  elif ! cmp -s "$vendored" "$src"; then
    echo "DRIFT: $vendored != $src"
    fail=1
  else
    echo "ok: $vendored"
  fi
done

[ "$fail" -eq 0 ] && echo "templates in sync" || echo "TEMPLATES OUT OF SYNC"
exit "$fail"
