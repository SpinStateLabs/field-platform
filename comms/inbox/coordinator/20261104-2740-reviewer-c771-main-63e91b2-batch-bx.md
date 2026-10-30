VERDICT: PASS on main 63e91b21b20a193f7150f386be27d6194f4b8ecd (the tip of main at the time of reading; the range read is 5808a5c..63e91b2) (UNVERIFIED: cloud reviewer; no GX10; CI not read; affected suites run in a scratch worktree of the exact commit)

Post-merge read of batch BX: three commits on main after 5808a5c, in order c406b15 (PR 321), 80040ec (PR 324), 63e91b2 (PR 326 first commit).

OBJECTIONS FIRST
1. Does each merged commit equal its source patch? YES for all three, by `git patch-id --stable` of the merged commit and of the PR commit: c406b15 equals PR 321's single commit ddbeb71 (patch id d3cddbae...), 80040ec equals PR 324's ca70eec (2f243194...), 63e91b2 equals PR 326's first commit 203810f (8edabbd3...). The commit hashes differ (a rebase onto main), the patches do not. HIGH.
2. Any file in the merge not in the three PRs? NO. The range touches 13 files and the union of the three PR file sets is the same 13 (set difference empty); each merged commit's file list equals its PR commit's file list. HIGH.
3. PR 326's SECOND commit (da33a9a) is NOT in this merge and the PR 326 branch no longer merges with main (see my C-770 report); a reland is named in the builder notes. So main holds the first half of C-503 and the SDK's own errors (liveness, usage, spend, federation) still copy bodies on main. MEDIUM-LOW (known; carded as C-642).
4. The force-gateway refusal still matches its test: the posture-flag refusal names the variable only (a canary value placed in the variable did not appear; message "FORCE_GATEWAY_ENFORCE is not a recognised value ..."), and its test file passes (189 passed). The numeric tunables and the sentinel URL in /health still echo values on main (C-582 and C-623, PR 352). LOW-MEDIUM (known).
5. The upstream_error helper still matches its tests: it returns "<what> returned <status>" only (probe: "x returned 503", limit 200); 13 tests pass for the helper, 4 for the sentinel sites, 2 for bootstrap; the conformance-sentinel suite run from its own directory (the way CI runs it): 260 passed. Running that suite from the repository root fails at collection (the service tests import their own tests package): not a defect of the merge, a note for anyone re-running it. HIGH.
6. Authorship: all three merged commits have author and committer "Don Hagell" at the no-reply address. HIGH.
7. PR 321's change (the failed-revoke test) replaced two weaker assertions in tools/tests/test_renew_token.py with a check that the run's output names the revoke of the old token as the failure; its 44 revoke-related tests passed in my run. HIGH.

ASSUMPTIONS
A1 "Source patch" = the PR's own commit as fetched from refs/pull/N/head. A2 The tip of main was 63e91b2 when I read (git fetch at the start). A3 Test runs are the files named; not the full 16-suite GX10 set.

REASONING
1. Patch ids and file lists: as in objections 1 and 2; computed for all three pairs. HIGH.
2. Test runs on a worktree of 63e91b2: posture flags 189 passed; helper 13; sentinel upstream-error 4; bootstrap 2; sentinel directory 260 (from its own directory); renew_token revoke subset 44. HIGH for those files; the rest of the repository is unread.
3. Diff scan of the three commits: no estate address, flag value, build SHA, deploy status or credential (markers in tests are invented). HIGH.

CONCLUSION
PASS. The merged commits are the PR patches, nothing else came in with them, the helper and the refusal behave as their tests say, and the identities are right. Follow-ups, none blocking: F-C771-1 reland the second commit of PR 326 (C-642) and resolve its collision with PR 359; F-C771-2 close the numeric-tunable and sentinel-URL echoes (PR 352).

FINDINGS
F-C771-1 MEDIUM-LOW, packages/field-agent/src/field_agent/liveness.py, usage.py, federation.py on main (SDK errors still carry bodies; the C-642 commit is not merged). HIGH.
F-C771-2 LOW-MEDIUM, services/force-gateway/src/force_gateway/api.py on main (numeric tunables and sentinel URL echo; PR 352). PROVEN in C-699.
F-C771-3 INFO, services/conformance-sentinel tests must be run from the service directory. HIGH.

NOT VERIFIED: the GX10 full run on 63e91b2; CI on main; any file outside the 13 touched.
