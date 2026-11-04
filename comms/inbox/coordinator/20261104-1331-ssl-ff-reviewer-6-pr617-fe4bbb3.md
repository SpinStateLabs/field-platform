# Reviewer ssl-ff-reviewer-6: PR 617 @fe4bbb3f (C-1127, C-110x: CHANGELOG delta for MERGE 1 to 15, main acaf5f24 to 05942b98; rebuild of #426) — UNVERIFIED (cloud, no GX10)

**VERDICT: PASS WITH CONDITIONS, head fe4bbb3f6a8f7d4e949b1ad00e26075a30de8ccc.** Docs only (CHANGELOG.md, +21 lines, 2 commits). Every number and commit id I checked is right; the open point is duplication with a section already on main.

## Objections first
1. Duplication (MEDIUM): main's existing section "main from 2026-10-30 to 2026-11-02 (commits f980f5c to cd3b769)" already describes much of MERGE 10 to 15 by theme. Counted: 37 commit ids that appear in that existing section also appear in this PR's new per-merge bullets. A reader of "Unreleased" gets the same change told twice (for example the C-1114 422 work, a9d1dd1 to 16cfff3 there, a9d1dd1f to 7708bd57 here). Not wrong, not marked as an alternate view.
2. A changelog of 145 commit ids is only as good as its ids: I checked all of them (below). Statements that cannot be checked from the repository ("merge evidence is in STATUS on the comms branch") I did not check.
3. Environment: the working clone was shallow when I started; I unshallowed (647 commits on main) before checking ids. Earlier "no merge base" or "not on main" readings in my other reports came from that shallow clone only; none of my earlier verdicts relied on ancestry (they compared trees and file content), and I re-checked the PR 411 statement: its commits 83f9fe06 and 896345e8 are not on main by sha, acaf5f24 is.

## Checked (HIGH, run by me, full history)
- Commit ids: 145 distinct 8-hex ids in the added lines; 145 resolve to commits; 145 are ancestors of main 97dcfec1; 0 unresolved.
- Ranges: every cited id lies inside its own merge range (previous tip..tip) for all 15 merges; the only ids outside are the base and tip SHAs written in the heading text, which are not claims about a commit.
- Counts: `git log --no-merges 9addf44f..05942b98` = 97 ("97 non-merge commits") ; `git log acaf5f24..9addf44f` = 90 ("90 commits"); per-merge commit totals: M1 8, M2 2, M3 18, M4 21, M5 6, M6 11, M7 21, M8 3, M9 13, M10 11, M11 13, M12 28, M13 20, M14 2, M15 13; each equals the number the bullet states.
- Subjects against claims: 31 spot-checked commit subjects (M3, M4, M5, M6, M7, M9, M14, M15 ids) say what their bullet says (examples: 87c8cd0e revoke idempotent and ledger-first; 49948328 environment_anchors check and repair; c4ac8c14 the edge-block opener ignores proxy variables; 7708bd57 unique per-service 422 test names). Merge 15 names eight services, as the commits and my own review of MERGE 15 found.
- Dates: STATUS dates MERGE 1 to 8 as 2026-11-01 and MERGE 9 to 15 as 2026-11-01/02; the headings say the same.
Count from the above: 5 check groups; 5 hold.

## Identity and public safety (HIGH)
Both commits (21907198, fe4bbb3f): author and committer Don Hagell 13129187+dhagell@users.noreply.github.com. 0 commits behind main, 2 ahead; applies cleanly. The added text has no estate address, flag value, build id, deploy status or credential (grep for deployed, live, armed, production, fly.dev, dotted quads: no hit).

## Conditions
1. State in one sentence that these per-merge bullets and the theme section above overlap (or drop the overlapping ids), so a reader knows it is one history told twice. 2. CI green on fe4bbb3f; GX10 "light run, docs only". After the PASS the head is frozen.
