# field-agent — Claude Code plugin

Everything Claude needs to implement a **compliant FIELD-governed agent**
with the `field-agent` client SDK: the three-hook knowledge (governed
actions, strict usage metering, fail-closed liveness), copy-paste
templates, operator bootstrap, the raw-REST path for non-Python agents,
and a compliance verification checklist.

Companion to the `field` plugin (Force-Field repo): **`field` is
design-time governance** — generate/validate/audit the FIELD manifest;
**`field-agent` is build-time integration** — put the agent's code under
that governance. They compose.

## What's inside

| Path | Contents |
|---|---|
| `skills/field-agent/SKILL.md` | core knowledge + the honesty rules that define "compliant" |
| `skills/field-agent/integration.md` | full hook API, env/ports, operator flow, troubleshooting |
| `skills/field-agent/rest-api.md` | non-Python integration + the five fail-closed rules |
| `skills/field-agent/checklist.md` | the `/field-agent verify` rubric (A–F, PASS/FAIL) |
| `commands/field-agent.md` | `/field-agent` — `new` · `verify` · `bootstrap` · `rest` · `env` |
| `templates/` | vendored verbatim from the monorepo — agent template, operator bootstrap, REST sample, manifest template + schema + a fully resolved example. Provenance: `templates/SOURCES.md` |

## Install

From this repo as a marketplace:

```
claude plugin marketplace add SpinStateLabs/field-platform
claude plugin install field-agent@field-platform
```

Or manually: copy `plugins/field-agent/` into a marketplace of your own, or
point `--plugin-dir` at it.

The plugin is knowledge + templates only — no MCP servers, no hooks, no
network access of its own. Runtime governance still requires a running
FIELD stack (see `packages/field-agent/demo.sh` or
`integration/demo/run_demo.sh` in the monorepo) and the SDK installed:
`pip install --no-deps -e packages/field-agent` (v0.1 needs the monorepo
checkout; `conformance-sentinel` is not on PyPI).

## Honesty line

The SDK — and therefore this plugin — is a **client, not an authority**.
An agent that never calls the SDK is not governed by it; the plugin's
checklist exists to catch exactly that. Enforced-vs-Declared table:
`packages/field-agent/README.md`.

## Keeping templates honest

`templates/` are byte-for-byte copies from the monorepo, stamped in
`templates/SOURCES.md`. Run `bash plugins/field-agent/verify_sync.sh` from
the repo root to detect drift; re-vendor when the SDK examples or
field-core templates change.
