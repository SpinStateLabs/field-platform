# Builder Lane 1: force-field MCP PR 1 (card id not assigned)

PR: https://github.com/SpinStateLabs/field-platform/pull/368 (draft). Head: 1f7f61f51e264566b708e49600bbe6f8b8b80966.
GX10: NOT RUN (cloud container; no GX10 access). CI: not yet observed.
Local: `services/field-mcp` 90 passed (3.13); `tools/tests` 3123 passed before fixes, affected files re-run 123 passed; mutants 29/29 killed (`scripts/mutants.py`, run on copies after the commit).

## Reviewer: attack these
1. A credential in any output: results, errors, stderr, stdout (stdio test checks the key and an upstream marker; redaction is a second line, not the control).
2. A URL taken from a tool argument: schemas are `additionalProperties:false`, no URL-like property name; base URL only from config and internal-only.
3. An upstream body in an error: errors are `<service> returned <status>` or fixed phrases.
4. A write reachable at Tier 1: the 7 POSTs are code-read only (introspect, oauth/introspect, crosswalk x3, replay x2); no live call proved them side-effect free.
5. A Tier 3 call: none exist; the 20 routes are written exclusions, and `FFMCP_ENABLE_DESTRUCTIVE` must not appear in the source (test).
6. Path arguments (dot segments, encoded dots), the `hosts.py` fallback predicate (C-489 not on main), the snapshot generator's `$ref` flattening, and `python-multipart` now present in the shared CI environment.

## Found beyond the route list
16 `/operator/*` routes (rotation-state GET, verify-hash POST on 8 services): excluded, hash oracle. `spend-governor POST /escalations/{id}/resolve`: Tier 3, excluded. My design note's grep count (96) missed these; live apps give 112 routes.

## Could not verify
GX10 and CI results; `runbatch.sh` edit (file not in repo); Python 3.12 and 3.14 installs of the hashed closure; any real service or MCP client; C-489/C-503 swap-in; whether the C-57 lint is satisfied for instance `.stream` calls beyond the passing test run (test passed).
