# MERGE 20 (PR 461 head itself: C-1163 v3, runbook stage pre-flight checklists on main as 2940dcca, d866b0d6, cddca526) - read-only fallback review, ssl-ff-reviewer-3

**FINDING SET (merged already): the cites I could check hold on main; 1 LOW. UNVERIFIED (cloud, no GX10).** Docs only; no mutants apply. Scratch checkout of origin/main 97dcfec1; nothing pushed.

## Objections first
1. A checklist that says "Nothing here has been run" can still name a path or flag that does not exist; each named artifact was checked.
2. Statements of who runs what rest on "Don's STAGES 1-4 RULING 2026-11-02": the repository holds the ruling text only inside this runbook (`grep` hits only the runbook), so I could not verify the ruling from a source other than the paragraph itself (not in source).
3. The paragraph says no soak floor is recorded for Stages 1-3; that is a negative claim: I checked `tasks/todo.md` for floors and found only the two it names.

## Facts (HIGH unless tagged)
- Commits 2940dcca, d866b0d6, cddca526: author AND committer Don Hagell noreply (checked). The three add +55 -1 in `docs/runbooks/v1.2-deploy-rollback.md` (the Stage 1-3 lists, the "who runs what" paragraph).
- Verified on main: `tools/operator_keygen.py` exists with `--check`; `tools/phase_g_check.py` has `--expect-mode` with `log-only` and `enforce`; `dropped_unauthenticated_records` is in `operator_auth.py`, `operator.unauthenticated` is in sealed-ledger api.py (the other two health field names appear only in a compiled .pyc in my tree, source not grepped by name: MEDIUM); `registry_edit` exists in the lifecycle-manager; the `svc-verifier-<estate>` name appears in the runbook and the runbook pin test; `tasks/todo.md` has two ≥ 5 min per-step lines and the two ≥ 25 h soak lines (512, 601) the paragraph cites.
- `tasks/stage0-keys.ps1` does not exist in this repository, but the runbook (line 1291) says it is Don's Force-Field script run on rog-command, outside this repo, so the "DON'S OWN" step is consistent.
- Runbook tests that read it: `test_runbook_pins_c465.py`, `test_deploy_docs.py`, `test_phase_g_check.py`, `test_operator_mounts_b6.py` = 168 passed on current main plus the 612 head (the same files; with `packages/field-agent/src` on the path).

## Findings
- F-M20-1 LOW (MEDIUM confidence): the health fields `dropped_refused_records` and `identity_present` were found only in compiled bytecode (source greps for the names inside `operator_health.py` matched only the .pyc in my tree; the grep scoped to `*.py` was not run), so I did not confirm them in source.
- F-M20-2 LOW: "Don's STAGES 1-4 RULING 2026-11-02" has no source outside this paragraph (not in source).

## Not done
No GX10 run. No claim about live state of any estate.
