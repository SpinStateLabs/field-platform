VERDICT: PASS WITH CONDITIONS on 1467e4e320902c9fe6810697eec07c7b96c9e711  (ssl-ff-reviewer-9; docs-only, read against GitHub and the repository; no tests applicable beyond the two the paragraph's neighbours use). Re-review of the condition fix for reviewer-10's PASS WITH CONDITIONS on 5f9d570c. Their C1 (the "Merged:" list incomplete for the commit it names) is fixed, with every added fact checked. The head conflicts with current main (the landing step), and one added fact is attributed to the wrong PRs.

R-PR612-1467e4e, PR 612 (rebuild of #465: runbook section 7, the Phase G "what is on main" paragraph). Applies to this head only. The fetched pull/612/head is 1467e4e3; 3 commits; one file, docs/runbooks/v1.2-deploy-rollback.md (+24/-17). The condition-fix commit changes the one paragraph. Base 97dcfec1 is 171 commits behind main.

OBJECTIONS FIRST
1. `git merge-tree --write-tree origin/main <head>` reports a CONFLICT (content) in docs/runbooks/v1.2-deploy-rollback.md (1 conflicted file, its three stage entries printed). The builder says so ("still CONFLICTING ... a merge is for the landing step"). The paragraph names main `6385f877` as the commit it was checked against and says later merges are not reflected, so whoever resolves the conflict must not take either side blind: main has moved 171 commits, including Phase G merges the paragraph's own note sends the reader to `tasks/todo.md` for. HIGH (measured). MEDIUM operationally.
2. One added fact is attributed to the wrong PRs. The paragraph now says "key rotation R1 to R3 (#53, #54: the operators file format 2 parser, verify-hash, rotation state, roster digest, break-glass counters)". On GitHub: PR 53 = "operators file format 2 parser (key rotation R1)", PR 54 = "Key rotation R2: verify-hash, rotation state, roster digest, break-glass counters", and PR 51 = "lifecycle-manager: per-request operator auth headers (key rotation R3)", MERGED. So R3 is #51, which the paragraph does not name, while the list it gives under "R1 to R3" is R1 and R2 only. The file's own CHANGELOG.md line 47 cites PR 51 for R3. The title promises "one PR per fact". LOW, HIGH confidence (checked with gh pr view).
3. The machine-verifier item is honest: it cites commits `583519d9` to `66aa8695` and says the PR number is "not checked here"; the builder explains why (GitHub PR 73 is "Merge batch B: PRs 71 and 72", not the verifier: I confirmed PR 73's title). The range holds 5 commits, all ancestors of main. HIGH.
4. The two "I do not know" phrases are now "not known from the repository" (the optional LOW is done). HIGH.

ASSUMPTIONS
A1 "Checked" below means: the PR is MERGED on GitHub with a title matching the item, and each cited commit is an ancestor of both 6385f877 and current main. A2 I did not re-verify the thirteen earlier PR numbers; reviewer-10 did (gh pr view, 2026-11-06).

REASONING / CHECKS
1. Diff read (5f9d570c..head): the paragraph adds #49 (DOA job rows folded into the roster example), #52 (signed operator events, failed record appends counted, "the GB10 Stage 1 blocker"), #53 and #54 (rotation), and the machine verifier commits; says the list is not exhaustive and points to tasks/todo.md; replaces two first-person phrases. Nothing else in the file changes. HIGH.
2. Facts, run: gh pr view 49, 52, 53, 54: all MERGED (2026-10-27, 10-28, 10-28, 10-28) with titles matching the items; commits cefb81b6 (#52), 3b3be059 (#49), b273d5bb (#53), c8ecba73 (#54), 583519d9 and 66aa8695 (P35): every one an ancestor of 6385f877 and of current main (git merge-base --is-ancestor: y on all six). HIGH.
3. Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. Nothing under .github/. A scan of the added lines found no address, key, hash of 40 characters or mailbox (commit abbreviations and PR numbers only). HIGH.
4. No test pins this paragraph; the builder ran test_runbook_pins_c465 and test_deploy_docs (43 passed, with all service sources on the path; the PR body notes 5 failures on a Windows box without them, same on main). I did not re-run them: the diff changes prose inside one paragraph. NOT VERIFIED by me.

CONDITIONS
C1 (required at landing) resolve the conflict with main by re-checking the paragraph against current main (what it lists as "not on main" may have landed since), not by choosing a side; re-run `environment_anchors.py --check` and the runbook tests on the merged tree.
C2 (small) name PR 51 for key rotation R3 (or say "R1 and R2 (#53, #54) and R3 (#51)").
C3 (standing gate) CI and a light GX10 run on this exact head; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
CI, GX10, the runbook tests on this head, the conflict's content beyond its existence, any estate fact (the paragraph states none).

CONCLUSION
Reviewer-10's C1 is fixed with facts that check out (four PRs merged with matching titles, six commits ancestors of main, the verifier's PR number honestly left out). Docs only, identity correct, nothing public-unsafe. Left: a merge conflict that needs a real re-check, and key rotation R3 credited to the wrong PRs. PASS WITH CONDITIONS: C1 at landing, C2 small, C3 the gate.
