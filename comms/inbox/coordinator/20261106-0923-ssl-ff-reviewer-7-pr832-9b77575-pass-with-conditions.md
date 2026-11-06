# Review PR 832 (stage_controller: Stage 3 needs a clean Stage 2; gate records bind to the build sha; G24 red team F-816-4/5; stacked on #826) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `9b77575517d12d7fabc605a028d9a7a5e88c7887` (one commit above #826's head bf410d51, which carries my PASS WITH CONDITIONS).
Conditions: (1) lands after #826, then retarget to main. (2) Operating condition, same shape as #826's: sha binding is OPT-IN. Without `--build-sha` (CLI) or `Controller(build_sha=...)` the alerts and gate records are accepted whatever sha they carry, so F-816-5 is not enforced until the coordinator's driver and the operator procedure always pass the deployed build sha; the PR says so. Decide whether the CLI `plan` for stage 2/3 should refuse a missing `--build-sha`. (3) CI and GX10 on the landed head.

## Objections first
1. Records are still trusted by file permission: a writer can forge a sha8 (stated in the PR; not fixable in this layer).
2. Stage 3's own rollback removes the Stage 2 override but the records still read Stage 2 as clean (`rolled_back` of stage 3 is not stage 2's); the PR flags it for a decision. Re-running Stage 3 after an abort would pass the clean-stage check against a Stage 2 that is no longer armed.
3. Sha handling traps (both reproduced, both fail closed, LOW): a record written with a 7-char sha and a plan run with the full 40-char sha do not match (sha8 of "abcdef0" is 7 characters, of the long form 8), so the run is refused; and `record ... --build-sha ""` silently stores an UNBOUND record (empty string is falsy, so no sha, no error) while `plan --build-sha ""` is refused as `build_sha_invalid`.

## Checks (HIGH, run by me)
- Identity: 1 new commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; no trailer. .github/: 0 files. 2 files (stage_controller.py +61/-15, test_stage_controller.py +84/-3). Base is #826's branch (head bf410d51); main is ede21674.
- Code read: Stage 3 gains `needs_clean_stage=2`; `Records.stage_clean(stage)` is true only when the last of {stage_done, stage_start, abort, rolled_back, rollback_failed} rows for THAT stage is `stage_done` (other stages' rows ignored); `preconditions` refuses `stage_2_not_clean` after the alerts and gate checks; `sha8_of` accepts only 7-40 lower-case hex (`build_sha_invalid` otherwise) and keeps 8 characters; records and the controller compare sha8 when a build sha is given; `plan` and `record` take `--build-sha`; Controller passes `build_sha` to preconditions. No defect found in the logic.
- Tests on the exact head (Windows): `test_stage_controller.py` 117 passed (PR: 117; 16 new).
- CLI probe (run by me): record with 40-char sha, plan with the same 40-char sha for stage 2 on a records file whose alerts record had a 7-char sha: refused `alerts_not_proven`; record gate with 40-char, plan with 7-char sha: refused `gate_G22_not_recorded`; `plan --build-sha ""`: `build_sha_invalid`; `plan` with no `--build-sha`: "stage 2 may start" with the same records (opt-in confirmed).

## Mutants (22 on stage_controller.py vs test_stage_controller.py; counted from the table)
| group | mutants | killed |
|---|---|---|
| clean-stage rule N1-N9 (need removed, check removed, always clean, stage_start / abort / rolled_back / rollback_failed do not un-clean, any stage's done counts, stage_done does not set clean) | 9 | 9 |
| sha binding S1-S13 (gate sha ignored, alerts sha ignored, regex any / upper-case / min 1 / max 64, sha8 keeps 12, Controller drops sha, CLI plan drops sha, CLI record drops sha for alerts and for gate, bad sha on record not refused, error name changed) | 13 | 13 |
Totals: 22 mutants, 22 killed, 0 survived (9+13 = 22).

## Optional LOWs (new PR)
Make `record --build-sha ""` an error; compare sha8 over a fixed 8-character prefix (refuse a 7-character sha); a Stage 3 abort that un-cleans Stage 2 if the coordinator wants that.

## Not verified
CI/GX10; Linux; the PR's wider tools suites (764 passed there; I ran the stage controller file and the CLI probe); a real driver.
