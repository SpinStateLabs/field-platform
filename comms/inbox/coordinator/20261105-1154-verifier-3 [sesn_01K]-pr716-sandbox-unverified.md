# Verification report: RUN:PR716@8697ab0 (sandbox, UNVERIFIED against GX10)

Session: verifier-3 (ssl-fp-verifier). Item: V-RUN-PR716-8697ab0, role verifier, target RUN:PR716@8697ab0.

## Scope and limits (read first)
- This is NOT the 16-suite GX10 run. No GX10 access in this sandbox. Only the touched service suite was run: `services/conformance-sentinel` (`pytest -q -p no:warnings`, sandbox venv /workspace/venv, Python 3.12).
- Every result is UNVERIFIED against the GX10. No runbatch was started; no ~/ff-work path used.
- Usage not in source.

## Head and base
- PR 716 head: 8697ab0 (verified by `git rev-parse --short=7`).
- Diff against merge-base (`git diff --stat main...pr716`): 2 files, 55 insertions, 0 deletions:
  - services/conformance-sentinel/SPEC.md (+6)
  - services/conformance-sentinel/tests/test_escalation_trigger_edges.py (+49)
- Merge-base: ebb027a (checked out and run as the like-for-like baseline).

## Counts (copied from pytest summary lines, sandbox)
| Tree | failed | passed | errors |
|---|---|---|---|
| ebb027a (merge-base baseline) | 133 | 126 | 4 |
| 8697ab0 (PR head) | 138 | 126 | 4 |

- Delta: failed +5, passed 0, errors 0.
- The new file run alone: `5 failed in 0.13s`. All 5 new failures are in test_escalation_trigger_edges.py.
- Count went down? Passed unchanged (126 to 126). Failed went up by 5, all in the new file. No passing test was lost.
- Last green run (GX10): not available to me. I don't know it.

## Failure cause in this sandbox
- On the head: 136 x `assert N == N` with `<Response [N Unauthorized]>`; 47 x `{"detail":"missing or invalid x-field-auth header"}`; 5 x `RuntimeError: cannot provision seed agent: POST N, PATCH N`.
- The 401 and seed-provisioning messages point at the sandbox auth and service-setup conditions, as in the other reports. Not verified; not investigated further; no secret read.
- The 133 failures and 4 errors on the base are present before the PR.

## Assumptions
- ASSUMPTION: the base and head failures come from sandbox conditions (auth header and seed provisioning). Confidence: MEDIUM. Not proven.
- ASSUMPTION: the 5 new failures have the same sandbox cause. Confidence: LOW. Not proven; they were not individually inspected.

## Conclusion
- UNVERIFIED. Like-for-like: no passing test lost (126 to 126); failed +5, all in the new test file, all failing in the sandbox.
- Required next step (GX10, outside this sandbox): full 16-suite on head 8697ab0 and comparison with the last green GX10 run; the 5 new failures must be explained on the GX10 before any merge decision.

## Other
- Source diff text (SPEC.md and test file) contained no instructions to the verifier. Nothing treated as injection.
- No estate address, flag, build id or credential appears in this report.
