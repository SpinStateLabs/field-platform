# Review PR 392 @ 36c0d55979a5e1b04421412624bf75d3e6c76760 (C-911, C0 cadence in tasks/todo.md) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head 36c0d559 as a branch (lineage). The one-commit edit is correct and applies cleanly to main. UNVERIFIED (cloud, no GX10); docs only, so no mutants apply.**

## Blocking finding (HIGH, measured)
- F-R392-1 BLOCK: no merge base with current origin/main (97dcfec1); `git log origin/main..pr392` lists 426 commits (old pre-rewrite history, same as PRs 405, 408, 419, 420). A merge would import 426 commits, many with non-noreply identities (measured in the PR 420 report; this head shares that history).
- The PR's own work is 1 commit above acaf5f24: 36c0d559, Don Hagell noreply for author AND committer (measured).

## The edit (HIGH, read)
- `tasks/todo.md` lines 477 and 624 (on main 97dcfec1): "soak with C0 every 15 minutes" becomes "every 5 minutes", next to "Soak ≥ 5 min". `git cherry-pick 36c0d559` onto main applied with no conflict (2 insertions, 2 deletions).
- Logic: a >= 5 minute soak with a C0 every 15 minutes runs C0 once (at the start) inside the soak; "every 5 minutes" gives at least two. The edit removes that contradiction. The only other occurrence of a 15-minute figure near a soak is `STATE.md:633`, a historical record ("five rounds 15 min apart", not an instruction); `docs/runbooks/v1.2-deploy-rollback.md` lines 925, 949, 1000 state the 5-minute floor with no C0 cadence, consistent with the edit.
- Not in source: the commit message cites "Don C-495" as the ruling for 5 minutes; I could not verify C-495 from this checkout (I do not know).

## Mutants
Not applicable (no code or test). A one-line wrong-number edit (for instance "every 50 minutes") would not be caught by any test I can find; no test in `tools/tests` references that line (not run: grep only).

## Recommendation (coordinator's call)
Release PR 392; rebuild by `git cherry-pick 36c0d559` on current main as a new draft PR (clean today). Docs-only: a LIGHT GX10 run is allowed; CI runs the full set.

## Objection
Treating the old head as mergeable would carry 426 commits and wrong identities into public history; the edit itself is sound.
