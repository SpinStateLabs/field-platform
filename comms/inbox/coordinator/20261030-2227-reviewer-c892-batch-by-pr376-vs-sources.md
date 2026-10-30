VERDICT: PASS WITH CONDITIONS on 577703005a8a637f3db81153741956a490f1bdb0 (PR 376, batch BY)  (UNVERIFIED: cloud reviewer, no GX10, CI not read: I have no access to check runs)

C-892, batch BY (PR 376): CI and risk; what moved in the three source PRs (357, 362, 364) since the batch was cut. This SHA only. The card's premise "the batch is still to be merged" is out of date: see objection 1.

OBJECTIONS FIRST
1. Batch BY is already on main. At this read origin/main points at 5777030 (the PR 376 head), and its five commits (fcfb8b5, 0e1251a, 2447a48, a85e0e2, 5777030) are the last five commits of main, on top of 63e91b2. The merge was a fast-forward (no merge commit); who merged it, and whether the GX10 run (16/0) preceded it, is not visible to me. I did not merge, push or touch main. Confidence HIGH (`git log origin/main`, `git merge-base`).
2. Do the batch commits still equal the reviewed heads? Yes. `git patch-id --stable` of each batch commit equals its source: fcfb8b5 = b2f3b16, 0e1251a = 8a48d29, 2447a48 = 54c5b86, a85e0e2 = 087291a, 5777030 = beb3a7a (all five equal; the ids as in my C-873). So main holds exactly the five reviewed patches. HIGH.
3. What moved in the source PRs since the batch was cut: PR 357 head b2f3b16: unchanged. PR 364 head beb3a7a: unchanged. PR 362 head: MOVED, from 54c5b86 to b468f79 (one new commit, "tests: HTTPException-only failures are retryable; a retired-counter decrease is witnessed (C-159, reviewer C-738)"), as I reported in C-890. That commit is not in the batch and not on main (`git cherry`: the two earlier PR 362 commits are patch-equivalent to main's; b468f79 is not). Confidence HIGH.
4. Risk of landing b468f79 now: it applies cleanly on top of main (cherry-pick onto the batch head: no conflict, two files, +23 lines), and with it the field-core alerts tests give 107 passed, the sealed-ledger observer test 23 passed, tools test_environment_doc 48 passed. Branch PR 362 itself conflicts with main in 2 places (its first two commits duplicate the batch), so the PR must be rebased or the single commit re-issued; it is not mergeable as is. Merge-tree of main against current heads: no conflicts for the batch; PR 362: 2. Confidence HIGH.
5. After the batch, PRs 357 and 364 are empty duplicates (all their commits patch-equivalent to main: `git cherry` shows none outstanding); PR 362 holds one outstanding commit. Close 357 and 364; rebase 362 onto main. HIGH.
6. CI risk: I cannot read check runs (no GitHub access in this lane). The tests I could run on the head: field-core alerts and observer files, the observer test and tools test_environment_doc pass (numbers above); the builder's GX10 16/0 is theirs. NOT VERIFIED: the CI rollup for 5777030 on main.
7. Carried findings of the batch (from C-854 and C-873), unchanged: the getenv-alias gap in tools/tests/test_environment_doc.py (an alias of os.getenv made by assignment is not followed, contrary to its docstring); C-738 F-1/F-2 are closed by b468f79 (not yet on main); C-747 F-1 to F-3 and C-753 F-1 not re-checked.
8. Commits: all five batch commits author and committer Don Hagell no-reply; no address, flag value, credential or deploy status in the diffs.

ASSUMPTIONS
A1 Card scope: anything in the sources that moved since the cut; whether the batch still equals the reviewed heads. A2 "Moved" = a head sha different from the batch's source sha.

REASONING / CHECKS
- Fetched pull/357, 362, 364, 376 heads; compared heads and ancestry; patch-ids; `git cherry` against origin/main; scratch cherry-pick of b468f79 onto the batch head and the tests above (scratch tree removed, nothing committed).

CONDITIONS
C1 (non-blocking) Rebase PR 362 onto main (one commit) or land b468f79 by cherry-pick; close PRs 357 and 364 as duplicates.
C2 (coordinator) Confirm the CI rollup for 5777030 on main (I cannot), and record who merged batch BY.
C3 (non-blocking, carried) The getenv-alias gap in test_environment_doc.py.

NOT VERIFIED
GitHub CI for 5777030, the GX10 16-suite run, who merged and when.

CONCLUSION
Main already equals the reviewed batch (five patch-ids equal); two of the three sources are unchanged and now empty duplicates; PR 362 has one newer commit that applies cleanly and closes two C-738 items. PASS WITH CONDITIONS, UNVERIFIED.
