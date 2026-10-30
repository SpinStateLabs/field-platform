# C-713 cloud read: file overlap of the open PR set, safe merge order (Lane 9; git probes RUN on fetched heads; UNVERIFIED on the GX10; no `gh`: the open list came from the public GitHub API)

VERDICT: 50 open PRs (all draft) at the heads below; 60 pairs share at least one file; 14 pairs CONFLICT textually (HIGH, `git merge-tree`), 46 merge clean pairwise. Five of the 14 are duplicates to close, four are one shared file (`docs/ENVIRONMENT.md`) that must be rebased in series, the rest are small. 35 PRs conflict with nothing. The batches "BY" and "BZ" are not defined in any source I have (STATUS names only BX = PR 350), so I give constraints and an order, not batch membership.

OBJECTIONS FIRST
1. Pairwise clean is not combined clean: three PRs that each apply to main can still conflict as a set (ENVIRONMENT.md is edited by nine PRs). I tested pairs only.
2. Textual merge is not semantic merge: `docs/ENVIRONMENT.md` first-read cells pin source lines and `tools/tests/test_environment_doc.py` fails when a merge moves one, with no conflict marker. Only the GX10 run shows that.
3. Several PRs are stacked or based on older mains (bases seen: 3ee2e5d, 48acfa6, 5808a5c, 7e8f16e, a9dc4f3, ad42410, b929f12); a base older than main is not a conflict by itself but is what `merge-tree` resolved here.
4. Readiness (reviewer PASS, GX10 16 suites, CI 7/7) is not judged here.

OPEN PR HEADS (public API at the time of the run): 57 30ac1e1 (held), 290 33b2c02, 297 3bb2510, 305 b484e7d, 308 fc8b363, 315 ba26a96, 316 6ae698f, 317 9cc5221, 318 4383a07, 319 34895a4, 321 ddbeb71, 322 935a8d0, 324 ca70eec, 325 34e7554, 326 da33a9a, 327 dc0fc85, 328 7679259, 330 ddc5551, 331 1a45db0, 332 0df2259, 333 39f8636, 334 8bea8c4, 335 fc73f64, 336 fe6c2be, 337 72e8fae, 338 f052a0e, 339 ab709ed, 340 bde88a2, 341 b6f9b61, 342 b03bf8d, 343 1f93620, 344 fd377ed, 345 f3787c9, 346 afb25af, 347 3c2d51c, 348 db9bad0, 349 50c87b9, 350 63e91b2, 351 af1e7cc, 352 3a525dc, 353 783a85f, 355 191affb, 356 846242e, 357 b2f3b16, 358 d5d4fc6, 359 dcff705, 360 3aacd5a, 361 5a58ee8, 362 54c5b86, 363 3b28331. Some of these are newer than the heads in cards; re-check a card's head before acting.

CERTAIN CONFLICTS (merge-tree, HIGH) AND WHAT TO DO
1. PR 305 x 308 (README.md, ROADMAP.md, STATE.md, docs/capstone-evidence/phase-3.md; 17 shared files): duplicates (coordinator decision C-493: 308 is the base): CLOSE 305.
2. PR 322 x 327 (ENVIRONMENT.md, federation-broker README, demo.sh, engine.py): duplicates (C-595): MERGE 322, CLOSE 327.
3. PR 315 x 318 (test_http_env_proxy_lint_c57.py) and 315 x 344 (http_env_proxy_allowlist.txt): 315 is the older version of the lint (the PR 315 vs 318 duplicate flagged in cycle 5): CLOSE 315 after 318 lands.
4. PR 318 x 330 (tests/test_lifecycle_headers_r3.py, one textual conflict): MERGE 318 FIRST, then hand-merge the R3 test file in 330 (builder Lane 1 has patches in comms/inbox/coordinator/*pr318-pr330-merge-fix.patch); api.py of 330 applies but leaves two `__init__` and two `send` if done blindly (C-660).
5. PR 326 x 350: 350 (batch BX) holds 326's first commit under another hash; land BX, then rebase 326 (or cherry-pick da33a9a): do not merge branch 326 (C-709).
6. `docs/ENVIRONMENT.md` in series: conflicts 326x330, 326x348, 330x348, 330x350, 348x350, 348x352. After BX (350): 330, then 348 (rebase, re-check cells), then 352 (rebase), then 326's delta; run test_environment_doc.py after each. PR 322 also edits the file (clean with all of them pairwise).
7. PR 308 x 337 (docs/ARCHITECTURE.md): merge 337 first, then rebase 308 (or fold the ARCHITECTURE.md lines).
8. PR 338 x 342 (docs/IMPLEMENTATION.md): merge one, rebase the other.

SAFE ORDER (constraints only)
BX: PR 350. Then, in any order that respects the stacks and series above: stack 328 -> 345 -> 353 (PR 329 is not open: redundant as decided); 318 -> 330 -> 348 -> 352 -> 326 delta; 322 (close 327); 337 -> 308 (close 305); 338 / 342 one at a time. CI-file PRs 319, 342, 346 each edit `.github/workflows/ci.yml` (clean pairwise): one per batch, HIGH CARE, GX10 plus CI each. Free of any textual conflict with every other open PR: 57 (held), 290, 297, 316, 317, 319, 321 and 324 (both inside 350: close after BX), 325, 328, 331, 332, 333, 334, 335, 336, 339, 340, 341, 343, 345, 346, 347, 349, 351, 353, 355, 356, 357, 358, 359, 360, 361, 362, 363. Clean shared files among them: 325 x 333 (claude-approver core.py), 324/341/350/352 (force-gateway api.py), 328/345/353 (compose tools, a stack), 336/344 and 315/336 (allowlist), 290/297/305/308/342 (tasks/ files).

FINDINGS
- F-C713-1 MEDIUM (process, PROVEN): close PRs 305, 327 and (after 318) 315, and 321 and 324 after BX: they conflict with, or are contained in, their replacements and keep reappearing as cards.
- F-C713-2 MEDIUM (PROVEN): `docs/ENVIRONMENT.md` is the serialising file: six conflicting pairs, nine editors. A batch that has two of {330, 348, 350, 352, 326} merges only with a rebase between them.
- F-C713-3 LOW: heads in some cards are stale (examples: PR 335 fc73f64 vs card 2e00c73; PR 337 72e8fae vs c3fd144; PR 340 bde88a2 vs 1643d20; PR 346 afb25af vs fb9dc61; PR 348 db9bad0 vs 6b685fd; PR 318 4383a07 vs c163ea2): reviewers' PASS verdicts on the old heads need a delta (some already carded as C-694).

NOT VERIFIED: three-way and N-way merges, semantic conflicts, test_environment_doc.py after any merge, readiness of any PR, the definition of BY and BZ.
CONCLUSION: land BX; close the five duplicates; serialise ENVIRONMENT.md PRs with a rebase and a doc-test run between each; keep ci.yml PRs one per batch.
