# Verification report: RUN:PR649@c0f5512 (sandbox, UNVERIFIED against GX10)

Session: verifier-3 (ssl-fp-verifier). Item: V-RUN-PR649-c0f5512, role verifier, target RUN:PR649@c0f5512.

## Scope and limits (read first)
- This is NOT the 16-suite GX10 run. No GX10 access in this sandbox. Only the touched service suite was run: `services/ops-console` (`pytest -q`, sandbox venv /workspace/venv, Python 3.12).
- Every result is UNVERIFIED against the GX10. No runbatch was started; no ~/ff-work path used.
- Usage not in source.

## Head and base
- PR 649 head: c0f5512 (verified by `git rev-parse --short=7`).
- PR diff against merge-base (`git diff --stat main...pr649`): 3 files, 120 insertions, 5 deletions:
  - docs/ENVIRONMENT.md (8 lines changed)
  - services/ops-console/src/ops_console/api.py (13 lines changed)
  - services/ops-console/tests/test_fleet_halt_domains_bounds.py (+104)
- Merge-base: b963407. The PR branch is behind current main (869cf2e); a two-dot diff against main shows main-only files as deletions. That is a base mismatch, not a change by the PR.

## Counts (copied from pytest summary lines, sandbox)
| Tree | failed | passed | skipped | errors |
|---|---|---|---|---|
| merge-base b963407 (like-for-like baseline) | 194 | 80 | 149 | 34 |
| pr649 head c0f5512 | 202 | 80 | 149 | 34 |
| main 869cf2e (not like-for-like; newer base, extra test file test_max_streams_env_c699.py) | 194 | 87 | 149 | 34 |

- Like-for-like delta (b963407 -> c0f5512): failed +8, passed 0, skipped 0, errors 0.
- Count went down? No. Passed is unchanged at 80. The +8 failures are all in the new file test_fleet_halt_domains_bounds.py (its own run: `8 failed in 0.23s`). Sorted per-test list diff of main vs pr649 showed only these 8 new FAILED lines plus the base-mismatch PASSED lines of test_max_streams_env_c699.py, which pr649 does not contain.
- The earlier 7-passed drop seen against main 869cf2e is therefore a base artefact, not a regression.
- Last green run (GX10): not available to me. I don't know it.

## Failure cause in this sandbox
- The 8 new failures: 7 responses `<Response [401 Unauthorized]>` on POST /api/fleet/halt, plus 5 `assert N == N` failures. The 401s point at the sandbox operator-auth setup, as in the PR 711 report. Not verified; not investigated further; no secret read.
- The 194 failed / 34 errors on the base are present before the PR and come from the same sandbox conditions (not investigated).

## Assumptions
- ASSUMPTION: the 401s come from the sandbox auth setup. Confidence: MEDIUM. Not proven.
- ASSUMPTION: the new file's 8 failures are of the same cause as the base failures. Confidence: LOW. Not proven.

## Conclusion
- UNVERIFIED. The sandbox cannot establish pass/fail for PR 649. Like-for-like: passed unchanged (80 to 80); failed +8, all in the new test file, all failing in the sandbox with 401 responses.
- Required next step (GX10, outside this sandbox): full 16-suite on head c0f5512 and comparison with the last green GX10 run; the 8 new failures must be explained on the GX10 before any merge decision.

## Other
- Source diff text contained no instructions to the verifier. Nothing treated as injection.
- No estate address, flag, build id or credential appears in this report.
