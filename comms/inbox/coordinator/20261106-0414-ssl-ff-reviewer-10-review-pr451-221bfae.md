# Review PR #451 (Fly redeploy checklist, C-1164) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `221bfae242a0a8d19c8a8420fdd27fb9cce0766c`.

## Facts (HIGH, read from the head)
- 2 commits (ac97f750, 221bfae2); 1 file: docs/runbooks/fly-redeploy-checklist.md (+88, new). Docs only; nothing under .github/; no deploy, token, flag or build values in the file.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The file states "plan only, nothing run" and says where it disagrees with `v1.2-deploy-rollback.md` the runbook wins. It also names what it does not know (soak floors, deploy SHA, label, memory size, volume id) instead of inventing them.
- The Q-97 F1/F2 fixes are present: the preamble says the coordinator runs every non-DON-ONLY step; the 4a rollback names the R1 down-migration and the F-R2 discarded-head record.

## Claims checked against the runbook and tools on the head (no test guards this text; I read the sources)
- Stage 4a before/prove/snapshot/deploy/verify match runbook section 5 steps 1 to 4 (build arg FIELD_BUILD_SHA, service-less smoke machine without `--port` or volume, one `ff_data` volume, `fly deploy -c integration/fly/fly.toml --image ... --ha=false`, `--expect-perimeter --expect-build-sha`, `continuity`, canary catalogue).
- Rollback matches section 6: F-R1 image only (saved fly.toml, Phase C or later, R1 down-migration with services stopped), F-R2 snapshot to a new volume with the discarded head recorded, snapshots 5 days by default with raising retention a Don cost call.
- Arming matches section 7 "Arming, Fly": `[env]` must not carry the operator variables; four per-daemon identity secrets plus FIELD_OPERATOR_REGISTRY imported together via `fly secrets import` on stdin; temp file plus `mv -f` into `/data/operators/` at 0600; `fly_identity_check.py --expect four`; `phase_g_check ... --expect-mode log-only` (`enforce` after REQUIRE); 4b rollback order (unset REQUIRE first, then REGISTRY; never by image alone); "file and identity secrets may stay"; single-container caveat.
- Tool flags exist: estate_probe `--expect-build-sha` (40 or 64 hex) and `--expect-perimeter`, `continuity`, `catalogue`; fly_identity_check `--expect none|four`; operator_keygen `--check` and "shown once"; phase_g_check `--expect-mode off|log-only|enforce`.

## Minor (LOW, optional; docs follow-up PR only, head is frozen after this PASS)
1. The open item is stated as "I do not know whether it is resolved". The runbook (section 7, OPEN ITEM) says RESOLVED for an unchanged re-provision since PR #46 and still open for one that changes owner or `manifest_ref`. The checklist is safe (it points to the runbook) but could say so.
2. `phase_g_check` step omits the runbook's `op.hdr` note (it carries the `x-field-auth` line the perimeter needs). A coordinator following only the checklist could hit a 401.
3. Claims that cannot be checked from the repo (the 2026-11-02 Stages 1-4 ruling; F-R2 marked DON-ONLY, which the runbook does not say): not in source, taken from the coordinator's rulings per the commit message. MEDIUM.
4. `fly_identity_check.py --expect none` in the smoke machine assumes the image entrypoint runs there; I did not run it.

## Conditions
None.

## Not covered
Nothing was executed (no Fly, no estate); did not review other runbooks or rebase on current main. Mutation testing does not apply to a docs-only change.
