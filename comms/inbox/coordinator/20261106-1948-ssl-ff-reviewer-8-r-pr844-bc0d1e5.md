# Review R-PR844-bc0d1e5: PR 844 (E4: v1.2 Review block and lessons from recorded Don rulings)
Head reviewed: bc0d1e503cc469dd3f397e3c99dc5a3eb4661ae8. Behind main (currently f7408db5); `git merge-tree` against main is clean (tree 991bdcdb), so the staleness below is semantic, not a textual conflict.

## VERDICT: PASS WITH CONDITIONS (one line of the Review block is false on current main)

## Checks (HIGH, run by me)
1. Identity: both commits (b6d3e629, bc0d1e50) author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 2 files (tasks/todo.md +10/-1, tasks/lessons.md +40).
2. Every commit id the Review block cites: 30 of 30 are ancestors of this head, and each commit's subject matches the phase it is listed under (checked by `git log -1 --format=%s`): A ff1f836b 6d7d4f3c 20528a04 f69f9ae4 e89d2895; B 00bd6440 9e5b6422 f1951684 017a10f8; C db5ad331 700301d4 e96dc890 135330ab; D 4b8b3523; F 3f828115 5ae36006 b6481181 c01b2bbd 5b183c14; G 629e8630 d853ef0f 1c14b523 68b06053 24453a2e f6c348f6 cefb81b6 fd0ac135 ede21674 75085ae3 9a2417c0.
3. "Code and docs only, no deploy status": the added text has no estate-status sentence (the only hits for "estate" and "flags off" are the F4 feature name and the code default).
4. Lessons spot check against the ruling files in comms (the PR says it built them from `*groomer-don-rulings*.md` and the lane-1 file): C-563 option (c) (guard plus tip clean-up, no history rewrite), D-12 (internal secret as a Stage 2 prerequisite, per-agent secrets later), D-18/D-19/D-20/D-21, PR 322, C-467, C-478, D-6 each appear in those files with the ruling the lesson states. I read 8 of the 20 lessons against the source; the remaining 12 I did not trace.
5. `tools/environment_anchors.py --check` 0 wrong rows; `test_docs_no_line_cites_sd1` 2 passed; `test_runbook_trust_cites_sd2` 2 passed.

## Condition
### C1 (MEDIUM): "Phase E: not merged on main at this review" is no longer true
The Review block says: "Phase E (the words): not merged on main at this review; only the source list docs/capstone-evidence/v2-one-liners-source.md is there." On current main `docs/capstone-evidence/v2-one-liners.md` IS present (commits dd5c64c7 "docs: v2-one-liners.md (E1) and the script that checks every cited test exists and names the word" and 625e867e "E1: v2-one-liners states no estate status ..."; PR 819 merged). The PR was written on base e125a878, before that landed, and merges textually without a conflict, so landing it as is puts a false line in tasks/todo.md.
Fix: update the Phase E line to cite dd5c64c7 and 625e867e (E1), say what E2 to E4 still lack, and rebase onto current main; re-check the other 29 ids are still ancestors (they are, ids only move forward).

## Observations (LOW)
- The lesson text names "Don ruled ..." on items I could trace; the 12 I did not trace carry the same risk the author states ("a reviewer should check line by line"): this is a statement of what Don said, so a wrong line is a misattribution. The author lists what was left out on purpose (D-31, D-16, D-25, open items); I checked that D-16 and D-25 are described in the ruling files as approvals of branch deletes, as the PR says.
- One ruling file carries the date 20261110 in its name (`20261110-1740-builder-lane1-don-rulings-asked.md`) although the session date is 2026-11-06; the PR cites it by that name, so it resolves, but the date prefix looks wrong (not this PR's doing).

## Not verified
The remaining 12 lessons against their sources; GX10; docs checks beyond the three I ran.

## Conditions to reach PASS
C1 in a new commit rebased on current main; identity re-check of the new head.
