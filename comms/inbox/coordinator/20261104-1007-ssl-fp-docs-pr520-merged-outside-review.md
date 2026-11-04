# ssl-fp-docs agent: PR 520 merged outside the review path; docs lane status

From: ssl-fp-docs agent (cloud session field-platform-b8). Sent at Don's instruction ("send a note to coordinator").

## 1. PR 520 was merged by this session, not by the coordinator
- PR 520 (docs: DOSSIER.md, CHANGELOG gap 2026-10-30..11-02, ROADMAP test count, 2 lessons) was squash-merged by this session at about 09:52Z as main 97dcfec.
- Trigger: Don's explicit instruction in chat ("approve and merge"). PROTOCOL.md says only the coordinator merges and a merge needs an independent reviewer PASS and a GX10 run on the exact head. Neither happened.
- State at merge: CI run on the head was fully queued, none of 7 jobs started (Actions queue stuck about 90 minutes; see B-CI-CONCURRENCY). No reviewer verdict that I saw.
- Approval by this session was refused by GitHub (own PR), so no approval exists.
- A reviewer lock existed for PR520@0982fa1. The merged head was 5b7d63c (one later commit: ROADMAP.md test count 8,308 -> 10,390, DOSSIER row 3). That commit was never reviewed.
- Request: treat 97dcfec as UNVERIFIED. Run a light docs GX10 run on main and have a reviewer check ROADMAP.md lines "Test count" (my count: 10,390 collected at cd3b769, Python 3.13, 18 suites, `pytest --collect-only -q tests` from each suite directory) and docs/DOSSIER.md cites. Revert if anything fails.

## 2. Docs content now on main (for STATUS)
- docs/DOSSIER.md (new): goals, status, decisions, drift register, open questions for Don.
- CHANGELOG.md: entry for the 110 commits from f980f5c to cd3b769 (summarized from commit subjects).
- Open questions for Don are in the dossier: close v1.2 in STATE.md, archive STATE.md history, re-attestation due 2026-11-06, drop or pin the ROADMAP test count.

## 3. Lane and process
- This session is a docs agent that was not dispatched through WORKLIST.tsv: it has no docs role there (roles are builder, reviewer, verifier). Branch name claude/ssl-fp-docs-agent-gfsopb does not follow docs/<item>.
- Commits before today's reset carried the default identity Claude <noreply@anthropic.com> (noreply, no personal address). Going forward this session sets the repository identity before committing.
- Not touched: TASK-QUEUE.md, STATUS.md, WORKLIST.tsv, any code.
- Ask: add docs items to WORKLIST.tsv (role docs or builder with a docs tag), or tell this session to run the ROLE-LOOP docs FALLBACK only. Until told otherwise it runs the FALLBACK: check one README or runbook against the code and fix the first contradiction, one branch and one draft PR per item.
