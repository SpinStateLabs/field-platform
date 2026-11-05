# Reviewer report: PR 646 @032ca35f (tools: estate_kill_watcher and estate_probe use fullmatch for agent, hash and sha, S3-18)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, absolute-from-worktree PYTHONPATH built per scratch worktree (':' separator). Tests-plus-fix PR: 4 one-line `.match` to `.fullmatch` changes and tools/tests/test_trailing_newline_estate_tools.py (+52). The PR base is b963407a; main is now aab217d3 and `git merge-tree` shows a clean tree (53747314).

## Verdict: PASS WITH CONDITIONS (head 032ca35fd1d04ee1bc927c56f11c01883546c20b)
Conditions: C1 GX10 16/16 on the head rebased on current main; C2 CI green. No code defect in the four changed lines. One of the four sites (the displayed build_sha) is unpinned (M4, LOW).

## Objections first
1. The bug class is wider than this PR: tools/volume_admin.py still applies `$`-terminated patterns with `.match` at five sites: `_MANIFEST_NAME.match` (lines 204, 223) and `_KEY_NAME.match` (lines 255, 286, 317) on this head. `$` matches before a final newline, so a name like `key\n` passes (HIGH, grep and reading; I did not run volume_admin). Those names reach file paths in an admin tool. Out of this PR's scope; a follow-up item (S3-18 sweep) is warranted.
2. tools/compose_resolved_check.py uses `.search` with `$`-ended patterns (A_HOME, FORBIDDEN_HOME_PARENTS and others): a trailing newline makes them match more, i.e. refuse more, which is the safe direction (HIGH, reasoned; not run).
3. tools/phase_g_check.py already uses `.fullmatch` on its `$` patterns (grep): consistent with the new rule (HIGH).
4. The pattern shapes themselves (agent length bound, hash and sha lengths and alphabet) are pre-existing and are only partly pinned: raising the agent bound to 500, allowing a space in an agent, a minimum hash of 8 or upper-case hex pass both the new file and the wider estate suites (P1 to P4 below). Not this PR's claim, listed so nobody assumes the PR pinned them (HIGH, run).
5. After the change a value with a trailing newline exits through the tools' own refusal path with the documented message (the tests pin the message text and exit code 2) (HIGH, run).

## Scope and identity
3 files: tools/estate_kill_watcher.py (1 line), tools/estate_probe.py (3 lines), tools/tests/test_trailing_newline_estate_tools.py (new, 52). 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): the new test file 9 passed. Mutants edit tools/estate_kill_watcher.py and tools/estate_probe.py one at a time; kill = the new file fails; for survivors I also ran the estate suites (test_estate_probe.py, test_estate_kill_watcher.py: 164 passed on the head); files restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | New file | Estate suites |
|---|---|---|---|---|
| M1 | watcher agent | `.match` again | KILLED | n/a |
| M2 | health sha | `.match` again | KILLED | n/a |
| M3 | continuity hash | `.match` again | KILLED | n/a |
| M4 | displayed sha | reply `build_sha` display `.match` again | SURVIVED | survived (164 passed) |
| M5 | watcher agent | check removed | KILLED | n/a |
| M6 | health sha | check removed | KILLED | n/a |
| M7 | continuity hash | check removed | KILLED | n/a |
| M8 | continuity hash | count 0 accepted | SURVIVED | KILLED (1 failed) |
| P1 | pattern bounds | agent length bound 500 | SURVIVED | survived |
| P2 | pattern bounds | agent may contain a space | SURVIVED | survived |
| P3 | pattern bounds | hash minimum 8 | SURVIVED | survived |
| P4 | pattern bounds | hash allows upper case | SURVIVED | survived |
| P5 | pattern bounds | sha any length 40 to 64 | SURVIVED | KILLED (1 failed) |
| P6 | pattern bounds | short sha accepted | SURVIVED | KILLED (2 failed) |

Counted from the table: 14 rows (watcher agent 2, health sha 2, continuity hash 3, displayed sha 1, pattern bounds probes 6). KILLED by the new file 6, SURVIVED 8. In the PR's claim (M1 to M7, the `.match` sites and their checks) 6 of 7 killed; the one survivor is M4, a display-only site where a trailing newline would be shown (LOW). M8 and P5 and P6 are killed by the existing estate suites; P1 to P4 survive everything and are out of the PR's claim. None judged equivalent.

## Findings
- F1 LOW (HIGH confidence, run): M4. Pin the displayed `build_sha` of a reply with a trailing newline (`<str, not shown>` form).
- F2 MEDIUM for follow-up (HIGH it exists, not run): objection 1, the five `.match` sites in tools/volume_admin.py.
- F3 LOW: objection 4, pin the agent length bound and alphabet and the hash length and case.

## Not verified
CI; GX10; volume_admin behaviour with a newline name (not run).
