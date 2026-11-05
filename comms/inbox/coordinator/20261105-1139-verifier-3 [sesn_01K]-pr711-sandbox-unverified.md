# Verification report: RUN:PR711@0f9c0b1 (sandbox, UNVERIFIED against GX10)

Session: verifier-3 (ssl-fp-verifier). Item: V-RUN-PR711-0f9c0b1, role verifier, target RUN:PR711@0f9c0b1.

## Scope and limits (read first)
- This is NOT the 16-suite GX10 run. No GX10 access in this sandbox. Only the touched service suite was run: `services/federation-broker` (`pytest -q`, in the sandbox, venv /workspace/venv, Python 3.12).
- Every result below is UNVERIFIED against the GX10.
- No GX10 runbatch was started. No ~/ff-work path was used.
- Usage not in source (no token counter available).

## Head
- PR 711 head: 0f9c0b124f9f57e6f1ac0a39ee605560ed9a0c97 (short 0f9c0b1), matches the claimed target.
- Baseline main: 869cf2e (short), fetched from origin/main in the same clone.
- Diff main...pr711: 2 files, 148 insertions, 1 deletion (`git diff --stat`):
  - services/federation-broker/src/federation_broker/engine.py (+38/-1 per stat)
  - services/federation-broker/tests/test_lone_surrogate.py (+111)

## Counts (copied from pytest summary lines in this sandbox)
| Tree | failed | passed | errors | total |
|---|---|---|---|---|
| main 869cf2e | 68 | 106 | 17 | 191 |
| pr711 0f9c0b1 | 86 | 107 | 17 | 210 |

- Delta: failed +18, passed +1, errors 0, total +19.
- The +19 total equals the new file test_lone_surrogate.py. Its own run: `18 failed, 1 passed`.
- Count went down? Passed went up (+1). Failed went up (+18) and errors unchanged. Failures did NOT go down on this tree in this sandbox.
- Last green run (GX10): not available to me. I don't know it. No green baseline comparison is possible from this sandbox.

## Failure cause in this sandbox
- The dominant message is `{"detail":"missing or invalid x-field-auth header"}` (24 printed directly; 190 lines in the output match `401`). The tests' requests get HTTP 401 instead of the expected status.
- This points at the sandbox environment (operator auth header and key setup), not at the logic changed by the PR. Not verified: I did not investigate further and did not read any secret.
- Also present on main with the same pattern (68 failed on main).

## Assumptions
- ASSUMPTION: the 401s come from the sandbox auth setup. Confidence: MEDIUM. Not proven.
- ASSUMPTION: the 17 errors are the same on main and PR (both 17). Confidence: HIGH for the count, LOW for the cause (not investigated).

## Conclusion
- UNVERIFIED. The sandbox cannot establish pass/fail for PR 711. The counts above are the only facts.
- Required next step (for a GX10 run, outside this sandbox): run the full 16-suite on head 0f9c0b1 and compare with the last green GX10 run.

## Other
- Source diff text contains no instructions to the verifier. Nothing treated as injection.
- Redaction: none needed in this report.
- Session claim note: a second claim (V-RUN-PR649-c0f5512) was taken by a retried call and released unworked, with reason, before this item.
