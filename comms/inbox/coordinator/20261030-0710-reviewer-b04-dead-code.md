# B-04: dead-code report (grep, report only, nothing changed)

Method: main 91bf0c7. Python AST over `packages/*/src` and `services/*/src` (16 components) for every `def` and `class` that is not a dunder and not decorated with a framework hook (routes, commands, validators, properties and the like). A name counts as referenced if the identifier appears anywhere else in the repo text (611 files: .py, .md, .yml, .toml, .sh, .html, .js, .json, .txt), counting def lines of the same name separately. Name-based, so it over-counts references when two things share a name; it cannot see dynamic dispatch (getattr, string names). Treat every row as a candidate to confirm, not a deletion list. No file was changed.

## Tier 1: the name appears nowhere except its own def (16 candidates)
| where | name | verdict |
|---|---|---|
| services/force-gateway/src/force_gateway/presets.py:59 | `component_block` | DEAD (grep: the only mention in the whole repo is the def); `preset_block` right below it is the live one. HIGH |
| packages/field-agent/src/field_agent/canary.py:314, field_client.py:73, packages/field-core/src/field_core/alerts.py:430 | `redirect_request` | NOT dead: urllib `HTTPRedirectHandler` hook on the `_NoRedirect` classes. HIGH |
| services/compliance-crosswalk/src/compliance_crosswalk/regwatch.py:191, 195, 199, 204 | `handle_starttag`, `handle_endtag`, `handle_data`, `handle_comment` | NOT dead: `HTMLParser` callbacks. HIGH |
| services/delegation-authority/.../cli.py:160, services/kill-switch/.../cli.py:147, services/lifecycle-manager/.../cli.py:168 | `auth_flow` | NOT dead: httpx `Auth` hook. HIGH |
| packages/field-core/src/field_core/delegation.py:41, ledger.py:89 and :183, services/attestation-reporter/.../engine.py:116, services/sealed-ledger/.../api.py:133 | `_omit_*` | NOT dead: `@model_serializer(mode="wrap")` (pydantic); my decorator filter missed `model_serializer`. HIGH |
So tier 1 holds exactly one real candidate: `component_block`.

## Tier 2: no reference in any `src` file besides the def, but used by tests, docs or other files
This tier lists production code that only tests keep alive. After removing framework hooks and name collisions (`main`, `_verify`, `_write`, `_read`, `_load`, `_check`, `_tick`, `_answer`, `_decide`, `_clean`, `_env`, `_migrate`, `Handler`, `do_GET`, `do_POST`, `log_message`, `list_agents`, `build_engine`, `set_policy`, `set_cap`, `observe`, `is_guarded`, `report_spend`, `report_usage_from` are used or are public SDK API; I spot-checked 14 of them with `grep -w`), the genuine candidates (name occurs once in src, at its def, and in tests or docs only):
| where | name | used by | note |
|---|---|---|---|
| packages/field-core/src/field_core/operator_auth.py:519 | `strip_reserved_unless_asserted` | tests (9 mentions) | docstring says "DEPRECATED (C-10): use admit_ledger_event". HIGH |
| packages/field-core/src/field_core/operator_auth.py:548 | `reject_reserved_event_type` | tests (8), docs (1) | docstring says "DEPRECATED (C-10): use admit_ledger_event". HIGH |
| packages/field-core/src/field_core/operator_auth.py:1232 | `reset_retired_memory` | tests (5) | test helper living in src |
| packages/field-core/src/field_core/alerts.py:208 | `reset_stats` | tests (2) | test helper living in src |
| packages/field-core/src/field_core/conformance.py:67 | `clause_text` | tests (4) | |
| packages/field-core/src/field_core/pricing.py:163 | `is_priced` | tests (6) | |
| packages/field-core/src/field_core/templates_api.py:33 | `schema_json` | tests (6) | |
| services/delegation-authority/src/delegation_authority/store.py:140 | `active_tokens_for` | tests (1) | one test only |
| services/spend-governor/src/spend_governor/core.py:594 | `resolve_escalation` | tests (2) | thin wrapper over `resolve_escalation_once` (line 598), which the API uses |
| services/compliance-crosswalk/src/compliance_crosswalk/regwatch.py:218 | `content_hash` | tests (4) | |
Confidence MEDIUM: these have no src caller by name; dynamic use is not excluded. `report_usage_from` and `report_spend` (packages/field-agent/src/field_agent/agent.py:129, 133) are public SDK methods used by examples and docs, so not dead.

## What this does not cover
- Methods called only through attribute names that collide with another def (hidden by the collision rule); functions referenced only by string (CLI entry points in pyproject, `getattr`).
- Dead branches inside live functions, unused imports, unused module constants, unused parameters. A real tool (vulture) was not run; not installed here, and I did not install anything.
- `tools/`, `plugins/`, `integration/` Python.

## Suggested cards (proposed, not queued)
D1 (Lane 1, small): remove `component_block` (presets.py:59) and confirm CI green. Done when the name no longer appears in the repo.
D2 (Lane 1): decide the two C-10 deprecated helpers in operator_auth.py (519, 548): delete them with their tests, or keep with a removal date in the docstring; today the tests keep security-looking dead code alive. Mutant check: the tests that fed them must still cover `admit_ledger_event`.
D3 (low): move `reset_stats` and `reset_retired_memory` behind a test-only module or underscore name so production code does not expose reset hooks.
D4: run vulture (or equivalent) once in a scratch venv at 80% confidence for the dead-branch classes above.

## What I did NOT do
- Change any file, install a tool, or run docker.
