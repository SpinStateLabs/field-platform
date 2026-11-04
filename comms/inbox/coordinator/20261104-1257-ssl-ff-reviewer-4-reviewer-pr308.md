# Reviewer report: PR 308 @ 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4 (Phase E "the words": E1 table, E-gate)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 9468b184 (old); 12 commits incl. 3 merges of main; 23 files (+962/-60): tools/e_gate.py (+301), tools/tests/test_e_gate.py (+164), docs/capstone-evidence/v2-one-liners.md (+356), plus wording edits in README.md, ROADMAP.md, STATE.md, service READMEs, fly files and incident-replay. Earlier reviews exist in comms (e.g. c972 PR 308 vs PR 305, groomer C-603 public-safety); I did not rely on them.

## Objections first (three are blocking as it stands)
1. MERGE (HIGH, run by me): `git merge-tree --write-tree origin/main pr308` reports a 3-way CONFLICT in ROADMAP.md. The PR rewrites ROADMAP.md (44 lines) and README.md/STATE.md rows that main has since moved; the E2/E3 checks of the gate read exactly those files, so a rebuild must re-run `python tools/e_gate.py` (full, not `--words-only`) on the rebuilt head.
2. IDENTITY (HIGH, run by me): commit a4cfe577 ("Merge remote-tracking branch 'origin/main' ...") has author AND committer `Don Hagell <dhagell@users.noreply.github.com>`, without the numeric id the other 11 commits carry (13129187+dhagell@...). The coordinator's PR 381 ruling allows re-authoring such a commit INSIDE a batch branch only (patch-id identical); it is a merge commit, so the batch would need to recreate the merge.
3. PROCESS: 7 of the 12 commits carry `Co-Authored-By: Claude Fable 5.1` (00e5f3f4, 07746493, 412b9b2c, 7265cace, 54cce678, 44fd9f31, 3298344d); the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailers are present; MEDIUM that a Fable session wrote them). Coordinator ruling needed.
4. The gate is not wired into CI: no workflow references `e_gate` (grep of .github on this head and on main), so "every Enforced word cites a test" holds only when someone runs it. Stated here, not a defect of the PR.
5. A word-checker that bans phrases by regex is a floor; the file says nothing about what it cannot see (synonyms of "certified", the same claim in a file outside README/ROADMAP/the E1 table).

## Verified (run by me)
- On the exact head: `python tools/e_gate.py` printed "E1: 12 systems, 80 Enforced citations, 40 Declared rows checked" and "E-GATE: PASS (0 problems)" with real git history (the cited commits are ancestors of HEAD and define the cited tests at the cited paths).
- Against current main's code: I checked out origin/main in a scratch worktree, added only this PR's tools/e_gate.py, tools/tests/test_e_gate.py and docs/capstone-evidence/v2-one-liners.md, and ran `python tools/e_gate.py --words-only`: E1 12 systems, 80 Enforced, 40 Declared, PASS. So every cited test still exists on main and still names its keyword (HIGH). The E2/E3 half was not testable that way because it reads the conflicting README/ROADMAP/STATE.
- tools/tests/test_e_gate.py: 18 passed (head). v2-one-liners-source.md (the "old" column's source) is already on main.
- I did not individually verify each of the ~20 wording edits in README/ROADMAP/STATE/service READMEs against the code; the gate's E1 checks cover the table, not the prose. Coverage statement: gate and its tests reviewed and mutated; the prose edits only spot-read.

## Mutants (mutations of tools/e_gate.py; scratch worktree on the head; baseline 18 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| 1 | negation window two words -> nine | 1 failed | yes |
| 2 | "never" no longer negates | 1 failed | yes |
| 3 | banned "certified" removed | 3 failed | yes |
| 4 | banned "compliant with" removed | 1 failed | yes |
| 5 | banned Force-Field spelling removed | 18 passed | NO |
| 6 | assert statements not counted | 7 failed | yes |
| 7 | pytest.raises blocks not counted | 2 failed | yes |
| 8 | bare strings count as assertion words | 18 passed | NO |
| 9 | any keyword accepted | 4 failed | yes |
| 10 | non-test function name accepted | 18 passed | NO |
| 11 | ancestor check dropped | 1 failed | yes |
| 12 | defines() accepts a prefix name | 1 failed | yes |
| 13 | old-sentence verbatim check dropped | 1 failed | yes |
| 14 | estate status must be Declared dropped | 18 passed | NO |
| 15 | systems 1-11 instead of 1-12 | 1 failed | yes |
| 16 | Enforced row vs Declared README not refused | 1 failed | yes |
| 17 | Declared reason length check removed | 18 passed | NO |
| 18 | global estate-status line check removed | 18 passed | NO |
| 19 | Declared row vs Enforced README not refused | 1 failed | yes |
| 20 | "209 tests" check removed | 18 passed | NO |
| 21 | README dropped from the words scan | 18 passed | NO |
| 22 | STATE "Phase E" check removed | 18 passed | NO |
| 23 | "RACI-ready" check removed | 18 passed | NO |
| 24 | PRODUCT/burn-in header check removed | 18 passed | NO |
Totals counted from the table: 24 mutants, 13 killed, 11 survived (5, 8, 10, 14, 17, 18, 20, 21, 22, 23, 24). Survivors run against the whole suite: nothing else imports or runs e_gate (no CI reference, no other test), so the 11 survive everything. Reading: 5, 10, 14, 17, 18 are E1/word checks with no test case; 20-24 are the E2/E3 half, which test_e_gate.py never runs (it calls `check_e1` and the words scan only); 8 is likely near-equivalent (a bare string inside an assert/raises block is the only place the skip matters).

## Findings
- F-PR308-1 PROCESS (blocking merge as-is): conflict in ROADMAP.md (objection 1); rebuild on current main, then full `python tools/e_gate.py` on the rebuilt head.
- F-PR308-2 PROCESS (blocking merge as-is): id-less identity on merge commit a4cfe577 (objection 2).
- F-PR308-3 PROCESS: Fable trailers on 7 commits (objection 3).
- F-PR308-4 MEDIUM-LOW: the whole E2/E3 half of the gate (README one-liner column, ROADMAP counts, "RACI-ready", PRODUCT/burn-in, STATE) has no test (mutants 20-24); a regression there passes silently. Add tests on small fixtures.
- F-PR308-5 LOW: mutants 5, 10, 14, 17, 18 (E1 and words checks without a test case); mutant 8 near-equivalent.
- F-PR308-6 LOW: the gate is not wired into CI (objection 4); decision for the coordinator.

## Verdict: PASS WITH CONDITIONS on 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4 (the gate's content PASS; merge blocked on F-PR308-1 and F-PR308-2)
Conditions: (1) rebuild on current main with the ROADMAP.md conflict resolved and the full e_gate run green on the rebuilt head (I have not seen it); (2) the id-less merge commit handled inside the batch only; (3) coordinator ruling on the Fable trailers; (4) CI green and GX10 16/16 (light run is not allowed: the PR changes a tool and fly files) on the rebuilt head. Not run by me: CI, GX10, the rebuilt head.
