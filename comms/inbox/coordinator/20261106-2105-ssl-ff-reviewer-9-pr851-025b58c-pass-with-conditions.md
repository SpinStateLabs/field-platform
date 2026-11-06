VERDICT: PASS WITH CONDITIONS on 025b58c43058d8b0c286f989ad5a17205f80e388  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Reviewer-8's two BLOCK items on PR 797 are fixed here; the conditions are Don's decisions and the standing gate.

R-PR851-025b58c, PR 851 (rebuild of PR 797 / #342, C-560 public-safety scrub plus scanning guard). Applies to this head only. gh pr view 851 confirms the live head.

OBJECTIONS FIRST
1. The rebuild's claim "net diff of PR 797 over its base, minus ci.yml" is checkable, so I checked it (item 1 below): the file lists differ only by .github/workflows/ci.yml, and the changed-line sets differ only by the four added allowlist lines the PR describes. HIGH.
2. The scrub rewrites two AGENT SKILL files (agents/ssl-invoicing-agent/SKILL.md, agents/ssl-timekeeping-agent/SKILL.md): the instruction line that dot-sources field-rest.ps1 from an absolute personal path becomes `. "<repo>\tools\field-rest.ps1"`. For a human, `<repo>` is a placeholder; for an agent that executes the skill text literally it is no longer a runnable path. No test pins these two lines. MEDIUM-LOW (I did not run the skills).
3. A guard that is a list of patterns plus a count-based allowlist proves shape absence, not meaning. Its own docstring says so (LIMITS: same-class replacement in a file with an unchanged count is invisible; encodings not covered; history not scanned). Accepted as stated, not a defect. HIGH.
4. Allowlist entries of kind decision, moves and reword may FALL below their count and never rise (problems() / tolerated_keys). So the stale-entry check does not apply to those kinds: lowering a file's actual count never fails. By design (C-758) and pinned by the tests; it means the new ci.yml entry (kind decision) can drift down silently. LOW.
5. The ci.yml comment (a /home/<account> shape) is deliberately NOT edited, because .github/ may change only by a concurrency block; it is counted by one decision entry. Don decides (rewording needs a rule exception). The PR states this. HIGH.
6. Three further allowlist entries were added for sites main gained since the old base (compliance-crosswalk api.py comment, kind reword; test_witness_url_scrub.py 6 userinfo fixtures; test_check_one_liners.py forbidden-phrase list). The fixture entries are plausible; the reword one is a code comment that states an estate setting as fact and stays public until reworded. LOW.
7. The PR body says the Windows-only PowerShell tests ERROR on the author's box and "CI is the judge" (CI skips them off Windows). On my Windows box they pass (item 4). HIGH on my run.

ASSUMPTIONS
A1 PR 797 head e4ea5559 and its base aab217d3 are as fetched (refs/pull/797/head). A2 The guard IS a test over the tracked tree, so adding a forbidden shape to a tracked file must turn it red; mutants on repository content therefore stand in for guard mutants.

REASONING / CHECKS
1. Net-diff identity: PR 797 (aab217d3..e4ea5559) = 25 files +1300/-144; PR 851 (f7408db5..025b58c4) = 24 files +1303/-143. diff of the two sorted file-name lists: only .github/workflows/ci.yml differs. diff of the sorted +/- changed-line sets with .github excluded from 797: exactly 4 lines more in 851, the four allowlist entries named in the PR body. HIGH.
2. Identity and scope: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. `git diff --stat -- .github` empty; none of the 24 files is under .github/. Merge base f7408db5, 6 commits behind main, `git merge-tree` clean. HIGH.
3. Non-test code touched is comments and docs only: .env.example, five runbook/notes files, compose gb10 comment, demo.sh comment, field-rest.ps1 comments, provision_ssl_agents.py docstring, claude-approver README. I read each hunk; no code line changed except the two SKILL.md instruction lines (objection 2). A scan of the added lines for private addresses, mailboxes, account paths and credentials found only checksum pins, <home> placeholders and the allowlist's synthetic-URL entries. HIGH.
4. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, from tools/): test_public_safety_c560 + test_windows_pins_without_powershell_c726 + test_environment_doc = 485 passed, 0 failed (169 s). test_field_rest_secret + test_ssl_renewal + test_operator_mounts_b6 = 78 passed, 0 failed (279 s): these are the files the PR says error on the author's box; here they pass. HIGH.
5. Guard mutants, run in a worktree of the head: each mutation applied to a tracked file (git add), then test_the_repository_matches_the_allowlist, kill = pytest failed; tree reset after each:

| id | mutation | result |
|----|----------|--------|
| C1b | a private IPv4 address added to README.md | KILLED |
| C2 | a Windows profile path added | KILLED |
| C3 | a /home/<name> path added | KILLED |
| C4 | a consumer mailbox added | KILLED |
| C5 | a corporate-domain mailbox added | KILLED |
| C6 | a URL with user and password added | KILLED |
| C7 | a Fly estate hostname added | KILLED |
| C8 | a unique-local IPv6 address added | KILLED |
| C9b | "on both estates" phrase added | KILLED |
| C10 | a CGNAT overlay address added | KILLED |
| C11 | an mDNS .local host added | KILLED |
| C12 | a tilde-name home added | KILLED |
| C13 | a hex private IPv4 added | KILLED |
| L1 | ci.yml allowlist entry count set to 0 | KILLED |
| L3 | witness-URL fixture count 6 -> 5 | KILLED |
| L4 | one-liners fixture count 1 -> 2 (more than found) | KILLED |
| L6 | crosswalk reword count 1 -> 0 | KILLED |
| L2 | ci.yml decision count 1 -> 2 (above actual) | SURVIVED (by design, objection 4) |
| L5 | crosswalk reword count 1 -> 2 (above actual) | SURVIVED (by design, same reason) |

Counted from the table: 19 run, 17 KILLED, 2 SURVIVED (both are the documented tolerated-fall rule, not defects). Two earlier attempts of mine were invalid and are not counted (a five-octet address; a phrase that does not match the guard's estate-state pattern): both re-run correctly as C1b and C9b. HIGH on the counts.

CONDITIONS
C1 (Don's decision, carried from PR 797) the ci.yml comment: leave it counted by the decision entry, or reword under a concurrency-only exception. Also the DOSSIER line and whether host-predicate sites are allowlisted or reworded (stated in the PR body; not mine).
C2 (non-blocking) confirm the two agent SKILL.md files still give a runnable instruction with <repo>, or pin it; I did not run the skills.
C3 (housekeeping) close PR 797 once this is accepted (the PR says so).
C4 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me. The head is frozen after this verdict except for a condition fix.

NOT VERIFIED
GX10 / Linux, CI, the skills' runtime behaviour, git history and other branches (the guard does not cover them either).

CONCLUSION
The rebuild is exactly PR 797's net diff minus ci.yml plus four allowlist entries, with the identity and .github defects of PR 797 gone: one clean commit, no .github file. 563 tests pass here, 17 of 19 guard mutants die (2 are the documented tolerated-fall rule). PASS WITH CONDITIONS (C1 Don's decisions, C2 optional, C3 housekeeping, C4 the gate).
