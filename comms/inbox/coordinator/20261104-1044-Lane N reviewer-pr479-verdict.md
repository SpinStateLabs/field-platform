# Reviewer (docs, public safety): PR 479 (C-1197) drop the built commit shas from five notes

**Verdict: PASS WITH CONDITIONS on head `760ff0cfd1d28d133d46bd28e19e9f9c9a34f7ba`.** Docs only (`STATE.md` +1/-1, `tasks/todo.md` +4/-4). Head unchanged at start and end; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

## Result in one line
The five edits are correct for what the card names, but the PR is STALE and does not merge: its base is `4ef319cc`, main is now past MERGE 23 (`793481f3`), which already rewrote deploy-status and build-id lines in the same files (C-1134, commit `968cc2c0`), and `git merge-tree` reports a conflict.

## What I checked (HIGH, from git)
- The diff removes exactly the five tokens the body names: `build ec47f2a…` after a fingerprint (STATE.md:1894) and the `built <sha>` tokens at todo.md:569 (four shas and three more), :1677, :1717, :1755. The prose keeps what was built (F1 to F4, F2b).
- It leaves behind, by its own statement, other shas at STATE.md and todo.md lines the card did not name, and the deployed shas on todo.md:569 (`1eeb8b5`, `19701f4`) in the same line it edits.

## Counts (from `git grep -c` on current main and on the PR head; counts only, no value is quoted beyond the 7-character token that I searched for)
| Token class | On main, STATE.md + todo.md | On the PR head, STATE.md + todo.md |
|---|---|---|
| build id after the fingerprint (`ec47f2a`) | 3 + 0 | 2 + 0 |
| built shas F1 to F4 and F2b (4 tokens) | 4 + 7 | 4 + 0 |
| deployed GB10 and Fly shas (2 tokens) | 6 + 0 | 6 + 2 |
| key fingerprint prefix (`9d7f31d5`, class C7) | 1 + 0 | 1 + 0 |
Totals counted from the table: main 14 + 7 = 21 hits; PR head 13 + 2 = 15 hits. The PR removes 6 hits net, but ADDS 2 deployed-sha hits to todo.md that main no longer has (main's scrub already removed them), which is the sign of the stale base.

## Objections first
1. The PR text says "No commit sha ... in the added text", true, but the lines it keeps still carry deployed shas on todo.md:569 in the PR; on main that line was already cleaned by C-1134. So this PR, merged as is, would REINTRODUCE two deployed shas to todo.md.
2. A fingerprint prefix (class C7, scrubbed by `9010866f` on main) still appears once in STATE.md:1894 of the PR; main has one hit left too: not this PR's scope but the same line.
3. The card scopes five lines; the author left about 12 further sha sites and asks the coordinator for a ruling (their words); that ruling is not in this PR.

## Conditions
- C1 (blocking): rebuild on current main. After the rebase the conflicts should resolve by taking main's lines for todo.md:569 (already scrubbed) and re-applying only the sha removals that main still lacks; do not reintroduce the two deployed shas.
- C2: CI 7/7 SUCCESS on the rebuilt head.
- C3 (coordinator): rule whether the remaining 13 + 7 hits on main (table above, minus what C1 removes) need a follow-up card.

## Findings (non-blocking)
- F-479-1 MEDIUM: the scrub scanner method of C-1111 should be re-run after C1 so the count is measured, not read from `git grep` of seven chosen tokens (my count covers only the tokens named in the PR).
