# Reviewer report: PR 451 @ ac97f750ba641105f25649e19a6a618540c96e23 (C-1164, WP7)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Docs only: one new file docs/runbooks/fly-redeploy-checklist.md (+84), one commit on base 05942b98. Author and committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). Merge with current main: `git merge-tree --write-tree` clean (HIGH). Only the sandbox fly.dev host and the sandbox image path `registry.fly.io/force-field-sandbox` (already in the runbook section 5) appear; no flag value, build id, deploy status or credential (HIGH).

## Objections first
1. A checklist that a person runs against a production-adjacent estate is only as good as its fidelity to the runbook; it restates sections 5, 6 and the Arming-Fly block, so any drift is a new defect and no test ties the two.
2. It lives in docs/runbooks/, while the runbook (v1.2-deploy-rollback.md:1599) says Stage 4 is run "only by the reviewed scripts and runbooks under `tasks/`"; I found no Stage 4 file under tasks/ on main, so this is the only one, but the location statement disagrees.
3. Several steps are only as safe as the tool being present in the image (see F-C1164-1).

## Verified against main
- Stage 4a "Prove the image", "Snapshot", "Deploy", "Verify" match runbook section 5 steps 1-4 (flags, `--ha=false`, build arg, no port and no volume on the smoke machine, one `ff_data` volume) (HIGH). Rollback matches F-R1, F-R2 and the 5-day snapshot note (section 6, lines 1079-1091) (HIGH).
- Arming LOG-ONLY and Stage 4b match the Arming-Fly block (lines 1598-1636): file by temp + `mv -f`, 0600, four identity secrets with the registry path through `fly secrets import` on stdin, one restart, `--expect-mode log-only|enforce`, rollback order REQUIRE first then REGISTRY, "never by image alone" (HIGH). `--expect none|four` exist (tools/fly_identity_check.py:210); `--expect-build-sha`, `--expect-perimeter`, `--expect-mode off|log-only|enforce`, operator_keygen `--check` exist; the permanent authenticated-fields statement is at runbook line 1664 (HIGH).
- The "open item" is correctly placed before Stage 3 (runbook line 1486), not Stage 4.

## Mutants (scratch worktree on the head, relative PYTHONPATH). Suite: tools/tests/test_deploy_docs.py, test_runbook_pins_c465.py, test_environment_doc.py. Baseline (head) 5 failed, 100 passed; main base 05942b98 also 5 failed (missing environment dependencies), not counted as kills.
| # | Mutant | Result | Killed |
|---|---|---|---|
| M1 | smoke check `--expect none` -> `--expect four` | 5 failed, 100 passed | no |
| M2 | rollback order swapped (REGISTRY first) | same | no |
| M3 | `--ha=false` dropped from the deploy command | same | no |
| M4 | DON-ONLY removed from the deploy go sentence | same | no |
| M5 | `--build-arg FIELD_BUILD_SHA=...` replaced | same | no |
| M7 | snapshot retention "5" -> "30" | same | no |
Totals counted from the table: 6 valid mutants, 0 killed, 6 survived. Excluded: my M6 (pattern did not apply) and M8 (no-op). Survivors against the whole suite: not run (no test references this file; grep found none). Expected for an unpinned runbook; I treat it as LOW, in line with the C-1187 ruling on checklist prose.

## Findings
- F-C1164-1 MEDIUM-LOW: the checklist says to run `tools/fly_identity_check.py --expect none` "inside the smoke machine" and `--expect four` "inside the machine", but the Fly image does not contain that tool (integration/fly/Dockerfile copies only tools/volume_admin.py and tools/estate_probe.py, lines 46 and 54). The tool's own docstring says it is uploaded with `fly ssh sftp`. A literal reader cannot run the step. Add the upload step.
- F-C1164-2 LOW: "Open item ... I do not know whether it is resolved" while the runbook (line 1716) states it: RESOLVED for an unchanged re-provision (PR #46), open for a changed owner or manifest_ref. Cite that status.
- F-C1164-3 LOW: location vs runbook line 1599 (tasks/); reconcile the sentence or the path.
- F-C1164-4 LOW: no pin test for the checklist (M1-M7).

## Verdict: PASS WITH CONDITIONS on ac97f750ba641105f25649e19a6a618540c96e23
Condition: F-C1164-1 fixed on this PR (a condition fix is the only push allowed), or the coordinator rules it a follow-up in writing; plus CI green and a GX10 light run "docs only" on the exact head rebased on current main. Not run by me: CI, GX10.
