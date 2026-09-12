# Template provenance

Every file here is a **byte-for-byte copy** from the monorepo, vendored at
commit `4df1cfc` (2026-08-29); `agent_template.py` re-vendored 2026-08-29
(cooperative-perimeter docstring line, checklist F1 — source and copy move
in the same commit); `manifest-schema.json` and `field-manifest-default.yaml`
re-vendored 2026-09-12 (FIELD 1.1.0 Enforcement Gate keys: optional
`enforcement.irreversible_actions`, `enforcement.protected_paths`,
`seal_algorithm` `sha-256-chain`, gate conventions in descriptions and a live
`tool_call` rate limit in the template — source and copy move in the same commit). The monorepo copy is the source of truth; when it
changes, re-copy and update this stamp. Drift check:
`bash plugins/field-agent/verify_sync.sh` (run from the repo root; wired
for exactly the mapping below).

| Plugin file | Monorepo source |
|---|---|
| `agent_template.py` | `packages/field-agent/examples/agent_template.py` |
| `bootstrap_operator.py` | `packages/field-agent/examples/04_bootstrap_operator.py` |
| `rest_api.sh` | `packages/field-agent/examples/05_rest_api.sh` |
| `field-manifest-default.yaml` | `packages/field-core/src/field_core/templates/field-manifest-default.yaml` |
| `manifest-schema.json` | `packages/field-core/src/field_core/schema/manifest-schema.json` |
| `example-manifest-invoicing-agent.yaml` | `integration/demo/manifests/invoicing-agent.yaml` |

Not vendored (read them in the monorepo): the per-hook samples
`01_actions.py` / `02_usage.py` / `03_liveness.py`, `run_all.sh`, and the
other three field-core manifest templates (`financial-agent`,
`read-only-agent`, `client-facing-agent` — the design-time `field` plugin
bundles those).
