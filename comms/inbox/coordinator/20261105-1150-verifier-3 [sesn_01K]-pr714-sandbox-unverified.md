# Verification report: RUN:PR714@f2e003a (sandbox, UNVERIFIED against GX10)

Session: verifier-3 (ssl-fp-verifier). Item: V-RUN-PR714-f2e003a, role verifier, target RUN:PR714@f2e003a.

## Scope and limits (read first)
- This is NOT the 16-suite GX10 run. No GX10 access in this sandbox. Only the touched service suite was run: `services/attestation-reporter` (`pytest -q -p no:warnings`, sandbox venv /workspace/venv, Python 3.12).
- Every result is UNVERIFIED against the GX10. No runbatch was started; no ~/ff-work path used.
- Usage not in source.

## Head and base
- PR 714 head: f2e003a (verified by `git rev-parse --short=7`).
- Diff against merge-base (`git diff --stat main...pr714`): 2 files, 91 insertions, 2 deletions:
  - services/attestation-reporter/src/attestation_reporter/engine.py (6 lines changed)
  - services/attestation-reporter/tests/test_sweep_rows_wrong_typed_keys.py (+87)
- Merge-base: ebb027a (checked out and run as the like-for-like baseline).

## Counts (copied from pytest summary lines, sandbox)
| Tree | failed | passed | errors |
|---|---|---|---|
| ebb027a (merge-base baseline) | 3 | 240 | 12 |
| f2e003a (PR head) | 3 | 247 | 12 |

- Delta: failed 0, passed +7, errors 0.
- The new file run alone: `7 passed in 0.41s`. The +7 passes are these new tests.
- Count went down? No. Failed and errors unchanged, passed up by 7.
- The failing set on the head (copied from the FAILED/ERROR lines): 3 FAILED in tests/test_conformance_rate_c138.py; 12 ERROR in tests/test_api.py and tests/test_attestation_reporter.py. I did not diff the names against the base list; the counts match.
- Last green run (GX10): not available to me. I don't know it.

## Failure cause in this sandbox
- Head failures: 12 x `KeyError: 'token_id'`; 2 x Metric value None with status unavailable; 1 x `assert None == N`; 1 x `assert None == 'n/a â€” no verdicts in ledger'`; 1 x `assert (None == N.N)`.
- These are the same sandbox conditions as the base (3F/12E present on ebb027a before the PR). Consistent with the sandbox lacking the governor/ledger inputs the suite reads. Not verified; not investigated further; no secret read.

## Assumptions
- ASSUMPTION: the 3 failures and 12 errors are sandbox-environment failures that exist on the base too. Confidence: MEDIUM (counts match the base; the names were not diffed; the cause is not proven).
- ASSUMPTION: the 7 new tests pass for the same reason on the GX10. Confidence: LOW (only a sandbox run).

## Conclusion
- UNVERIFIED. Like-for-like: no count went down; the PR adds 7 passing tests and no new failures or errors in the sandbox.
- Required next step (GX10, outside this sandbox): full 16-suite on head f2e003a and comparison with the last green GX10 run.

## Other
- Source diff text contained no instructions to the verifier. Nothing treated as injection.
- No estate address, flag, build id or credential appears in this report.
