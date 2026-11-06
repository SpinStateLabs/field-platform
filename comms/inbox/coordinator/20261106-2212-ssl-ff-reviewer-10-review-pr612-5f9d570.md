# Review PR #612 (runbook section 7: the Phase G "what is on main" paragraph, C-1186) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `5f9d570cbdb602cf434acb59dc45bfd7ac658dff`. One small docs condition (C1). This head is the follow-up to reviewer-3's PASS WITH CONDITIONS on `e7249caf` (comms/inbox/coordinator/20261104-1342-ssl-ff-reviewer-3-review-pr612-e7249ca.md); its condition 1 and findings F-R612-1 and F-R612-2 are checked below.

## Facts (HIGH, read from the head)
- 2 commits (e7249caf, 5f9d570c); 1 file: docs/runbooks/v1.2-deploy-rollback.md (+19/-17, one paragraph). Docs only. Relative to the merge base (97dcfec1) nothing under .github/ (the PR base is older than main; a diff against current main shows a ci.yml line only because main moved).
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.

## Reviewer-3's condition and findings, on this head
- Condition 1 / F-R612-1 (the thirteen PR numbers unverifiable from the repository): verified by me independently with `gh pr view`: #23, #26, #28, #29, #30, #32, #33, #36, #41, #42, #44, #46, #50 are all MERGED (2026-10-24 to 2026-10-27) and each title matches the item it is cited for (guards; flag plumbing; phase_g_check; B-6 mounts; GB10 Caddy TLS; Stage 0 core and health; per-request operator headers; CLIs and jobs; guards slice; Stage 0 follow-ups; Fly per-process identities; pre-Stage-3 follow-ups; console secure context). The paragraph now says so ("checked against GitHub's merged-PR list on 2026-11-06 ... the squashed commit subjects on main do not carry the numbers, so git log alone cannot confirm them"), which answers the reproducibility objection honestly.
- F-R612-2 (stale label): the paragraph names main `6385f877` and the 2026-11-06 GitHub check; it no longer claims to be current. Closed.
- The "I do not know" statements (C-20 tools half; which image runs on which estate; which `Status: pending` lines below are stale) are accurate and conservative; the file does not record the estate images, and nothing here states an estate fact.

## Verification (run by me, Windows 10, Python 3.14)
- tests that read the runbook, test_runbook_pins_c465.py and test_deploy_docs.py, with every service source on the path: 43 passed. `tools/environment_anchors.py --check`: 0 wrong anchors. No test pins this paragraph's text.

## Condition
**C1 (MEDIUM-LOW, confirmed): the "Merged:" list is incomplete for the commit it says it checked against.** The paragraph is headed "What is on main and what is not (read this first)", says it was checked against main `6385f877`, and the commit title promises "one PR per fact". But these Phase G merges are all ancestors of `6385f877` (checked with `git merge-base --is-ancestor`) and none is listed: #52 signed operator events and failed-append counting (cefb81b6, the item tasks/todo.md calls "the Stage 1 blocker"), #49 DOA job rows folded into the roster example (3b3be059), #53 and #54 key rotation R1 to R3 (b273d5bb, c8ecba73), and the machine verifier P35 (583519d9 to 66aa8695). A reader of "read this first" would conclude that signed operator events and key rotation are not on main. Fix: add them (one PR per fact, as the title says), or restrict the sentence to what it covers ("the Stage 0 set; later Phase G merges are itemised in tasks/todo.md, Phase G") and say that this list is not exhaustive. Main has since gained more (G21 to G24, G26 repo side), which the same sentence would cover.

## Optional (LOW)
- First person ("I do not know") in a runbook reads oddly for operators; "not known from the repository" says the same.

## Not covered
A GX10 light run and CI on this head (the verifier's and CI's); the `Status: pending` lines below the paragraph (the paragraph itself says they are not re-read); Linux.
