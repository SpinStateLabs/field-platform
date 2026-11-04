# Reviewer report: PR 457 @ 85fa7d15cb129cd35891e13ea2cd52e8e3d6f87c (C-1173 part 1, Q-93 F-Q93-2)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on base b39287c1, tests only (+22 lines in tools/tests/test_422_handler_installed_c1114.py). Author and committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). Values in the test are made up; no estate address, flag, build id or deploy status.

## Objections first
1. The base is b39287c1; main is now past it and the same test file changed on main (aed915d5 C-1183, cd3b7690 C-1189, 2349eeb5 C-1128). `git merge-tree --write-tree origin/main pr457` reports a CONFLICT in tools/tests/test_422_handler_installed_c1114.py (HIGH). This head cannot be fast-forwarded as it stands.
2. The delegation-authority validator raises a constant string ("provide exactly one of ttl_seconds or expires_at", services/delegation-authority/src/delegation_authority/api.py:93), so the test cannot show that a validator message built FROM the value is dropped; it shows only that the handler replaces whatever text with "Value error" (MEDIUM: the claim "never the value" rests on the msg replacement plus the no-input/no-ctx key check, not on a value-bearing validator).
3. One service, one validator kind: assertion errors (`kind.startswith("assertion")`, http_errors.py) and other custom kinds are not exercised.

## Verified
- Head unchanged at 85fa7d15. Baseline on the head: 26 passed (relative PYTHONPATH, all services/*/src plus field-core and field-agent).
- The test's marker is in a VALID field (agent_id), so it only appears in a response if the handler echoes `input` or ctx; the second request with a different marker and equality of the two detail lists pins that the reply does not depend on the value.

## Mutants (scratch worktree on the head; baseline 26 passed subtracted; "killed by new test" = the new test fails)
| # | Mutant (field_core/http_errors.py unless noted) | Result | Killed by new test | Also killed by older tests |
|---|---|---|---|---|
| M1 | value_error msg echoes the validator text | 1 failed | yes | no |
| M2 | fixed text "Value error" -> "Value error!" | 1 failed | yes | no |
| M3 | output adds `input` | 10 failed | yes | yes (9) |
| M4 | output adds `ctx` | 10 failed | yes | yes (9) |
| M5 | `type` blanked | 1 failed | yes | no |
| M6 | `loc` dropped | 10 failed | yes | yes (9) |
| M7 | value_error branch removed (falls to "Invalid value") | 1 failed | yes | no |
| M8 | msg = fixed text + input | 1 failed | yes | no |
| M9 | loc root-name test inverted (body redacted) | 10 failed | yes | yes (9) |
| M10 | status 422 -> 400 | 10 failed | yes | yes (9) |
| M11 | delegation-authority api.py: install_validation_handler removed | 4 failed | yes | yes (3) |
| M12 | delegation-authority api.py: validator no longer raises | 1 failed | yes | no |
| M13 | loc gains the stringified input on value_error | 1 failed | yes | no |

Totals counted from the table: 13 mutants, 13 killed by the new test, 0 survived; 7 (M1, M2, M5, M7, M8, M12, M13) are killed by the new test alone, so the PR adds real coverage over the nine type-error cases. No survivor to run against the suite. I did not run the other 15 suites.

## Findings
- F-C1173-1 HIGH (procedural, blocks merge as-is): textual conflict with main in the test file; rebuild on current main (the coordinator already ordered PR 457 rebuilt after 470/cd3b7690). Content is unaffected; patch-id of the added test block should stay identical.
- F-C1173-2 LOW: objection 2 (constant validator text) and objection 3 (assertion kinds not covered); optional follow-up in a new PR.
- Check I made and am NOT reporting as a result: I overwrote main's test file with this head's and two older-base tests failed; that is an artefact of the overwrite (NOT_YET lists changed on main), not evidence about the PR.

## Verdict: PASS WITH CONDITIONS on 85fa7d15cb129cd35891e13ea2cd52e8e3d6f87c
Conditions: (1) rebuild on current main and resolve the conflict in test_422_handler_installed_c1114.py (a rebuilt head needs its own check that the added test is byte-identical and that the file still passes: I have not seen the rebuilt head); (2) CI green and GX10 16/16 on the rebuilt head. Not run by me: CI, GX10, the rebuilt head.
