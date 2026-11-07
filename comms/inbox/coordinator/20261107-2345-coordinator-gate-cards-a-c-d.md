# Gate-closing cards for Phases A, C, D (coordinator, 2026-11-07; source: tasks/todo.md on main 2bc5643e, "Partial (reconcile 2026-11-04)" notes under each gate)

These are the evidence gaps the reconcile left under the A-, C- and D-gate lines. Gates themselves close only through the Gate template (steps 1-12) and Don; these cards only produce the missing evidence. Docs and reports only: no estate access, no deploy, no flag change. Public repo: no estate addresses, build ids or credentials.

## B-GATE-A1 (builder, docs, size S)
Gap: A-gate line (todo.md ~875): "in-repo tasks/lessons.md lacks the 'probe /health from a separate call' rule (STATE.md:409: lives in parent-folder lessons.md)". Task: read STATE.md around line 409 for the rule's wording and its reason (the rule is the one learned from an earlier health-probe mistake), add that rule to the in-repo tasks/lessons.md as a dated addition-only entry citing the STATE.md line, check git log for an open PR that already did it first, one draft PR. Verify: git grep -n "separate call" tasks/lessons.md finds the entry; docs lints in tools/tests pass.

## B-GATE-D1 (builder, docs/check, size S)
Gap: D-gate line (todo.md ~1660): "plugin.json now 0.1.6 (>= 0.1.2) but SOURCES.md stamp not checked". Task: find plugin.json and the SOURCES.md stamp in the repo (git grep SOURCES.md), compare the stamp with the plugin version and with the vendored manifest, run verify_sync.sh from the repo root (it must run from the root; see memory field-platform-local-test-env), and report the result. If the stamp is stale, fix it in one draft PR; if it is fine, file a report only (no PR). Do not touch the plugin version.

## V-RUN-DEMO (verifier, report only)
Gap: A-, C- and D-gate lines each want "run_demo.sh exit 0 + last 10 lines into STATE.md" and "demo wall times"; the reconcile found a tail only for A (STATE.md:443, exit 0 in 33 s). Task: on the GX10, run run_demo.sh on current main (one run), record the exit code, the wall time and the last 10 lines (run_demo.sh boots 7 local services and never starts lifecycle/attest/crosswalk; say so as STATE.md:443 does), file the report. No STATE.md edit; the coordinator does that.
