VERDICT: PASS WITH CONDITIONS on defb7eaf5c705a820471b1c8904d1f3c4d44d167

Reviewer Lane 15, cloud-reviewer, C-907, PR 383 at the new head (two commits: 2b22bac, defb7ea). UNVERIFIED: no GX10, CI not read. Settings names only; no value printed.

## Objections first
1. Premise: the card says "after reviewer C-43 (PASS WITH CONDITIONS)". Two C-43 reports exist for this PR: Lane 4's PASS WITH CONDITIONS on 2b22bac (three findings) and Lane 4's later PASS on defb7ea. My C-888 (also on 2b22bac) had four conditions. The head is no longer the one either of those PASS WITH CONDITIONS reports covered (HIGH).
2. The only conflict left is a merge conflict, not a code defect: this PR conflicts in docs/ENVIRONMENT.md with PR 352 (6f30657) and PR 381 (b00bd96). Probed with merge-tree: conflict with both, clean with 369, 374, 375 and with origin/main. Whichever merges first, this PR must be rebased (HIGH, run).
3. Log-only is still "not open" by decision, now stated in the module docstring (startup.py:9-13) and pinned. That is a ruling dressed as documentation: with the perimeter secret set and the operator layer in log-only, the service prints no operator line. Don may still want it named (MEDIUM, decision, not a defect).
4. An open warning is one line per service name per process; under several workers each prints one, and I did not test uvicorn's own log setup (not verified).

## Conditions (C-888 and the C-43 findings), each at the head
- C-888 C1 (log-only: name it or say it does not count): CLOSED by docstring, packages/field-core/src/field_core/startup.py:9-13, and by a tools test for every service with an operator layer (the commit says so). Probe: perimeter secret set, operator mode log-only, 14 real create_app calls: operator setting not named (2 services print another open setting, names only) (HIGH, run).
- C-888 C2 (pin the widening mutant in the tools file): CLOSED. Mutant "anything but enforce counts as open" on startup.py: tools test file alone 8 failed (it survived before); with all three files it fails at the first test (HIGH, run).
- C-888 C3 (the existing echo of a bad FIELD_OPERATOR_REQUIRE value, then at operator_auth.py:268): CLOSED. The message is now fixed text, packages/field-core/src/field_core/operator_auth.py:269-270 ("... is not one of 1/true/yes/on or 0/false/no/off; treated as ENFORCE"). Probe: a marker as the value of FIELD_OPERATOR_REQUIRE, FIELD_LEDGER_REQUIRE_SIGNING, FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE and enforce flag across all 14 real create_app runs: 14 of 14 print the open line, marker present in the output of 0 services. Secret = marker plus log-only: 0 leaks (HIGH, run).
- C-43 F-C43-1 (name guard end anchor and 64/65 length boundary unpinned): CLOSED. Mutants: match for fullmatch, length 65 and 63 limits, string-type guard dropped, perimeter check off, operator check off: 6 of 6 killed (HIGH, run).
- C-43 F-C43-2 (mistyped value echoed at start): CLOSED, see C3.
- C-888 C4 / C-43 F-C43-3 (docs/ENVIRONMENT.md merge order against PR 381 and PR 352): OPEN (objection 2); the PR's own change to that file is 44 table lines.

## Does any service log a flag value or secret in the warning?
No. The line formats names only (startup.py name filter: 1 to 64 UPPER_SNAKE characters, whole-string match); with markers set as the value of the four non-secret settings, and with the marker as the secret, nothing in stderr of any of the 14 services contained it (HIGH, run; every service built through its real create_app in a clean process).

## Overlap with PRs 369, 374, 375
merge-tree of this head with each head: no conflict (HIGH, run). I did not run a combined suite; PR 369 and 374 do touch services' perimeter code, so the interaction of "secret set" semantics with 369's read key was not re-tested here (not verified).

## Evidence
- 285 tests passed across field-core startup, operator_auth stage0, tools startup warning and the environment-doc test on a scratch tree (HIGH, run). Commit author and committer: the no-reply Don Hagell identity on both commits (read). The commit-identity script printed "clean (0 commits)", so it is NOT evidence; the author lines are.
- Files restored; worktree removed.

## Conditions
1. Rebase onto PR 352 and PR 381 (or them onto it) and re-run test_environment_doc.py: blocking for merge order only.
2. Decide log-only (objection 3): non-blocking.
3. Re-check behaviour under uvicorn log config: non-blocking.
