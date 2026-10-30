VERDICT: PASS WITH CONDITIONS on 2d6a16725de29811887825f338f24bc88b6a6736

Reviewer Lane 15, cloud-reviewer, C-906. UNVERIFIED: no GX10, CI not read. Scratch tree, counts and line numbers only; no value printed here.

## Objections first
1. "Scrub complete" is false for one of the card's own tests: the soak rule. Three soaks still read one hour at docs/runbooks/v1.2-deploy-rollback.md:925, :949, :1000 (C-870 F-C870-4). PR 379 does not touch them; PR 290 / batch BZ (PR 386) carry the fix (HIGH, sweep). The card's "soak times five minutes" check therefore FAILS on this head alone.
2. Deploy-status sentences remain: :484 ("Seen 23/23 on the GB10 ... and on Fly", dates and builds now placeholders but the observation stays), :1636 ("every image deployed today"), :1093 heading "NOT armed on any estate". C-870 F-C870-3 listed :484-485 and :1636 and :1093 as deploy status; the builder's note names only dates and timestamps as fixed and does not claim these. Whether they count as "deploy status" under Don's ruling is MEDIUM; I count them as open.
3. C-870 C4 not done: no line says a deploy needs Don's approval in chat at the start of section 2 (:60) or section 5 (grep for "in chat": 0 hits); the five "Don's go" lines are the arming steps only (:944, :968, :975, :1389, :1546). The builder says a separate docs card (HIGH, grep).
4. Remaining ISO dates (9 lines: :3, :477, :480, :665, :1059, :1064, :1735, :1736, :1803) are document, ruling and proposal dates and one image-capability date at :1059 ("from <date> on; older images do not"), not dated deploy observations (MEDIUM; :1059 is the closest to build-state and could be placeholdered).

## C-870 conditions
- C1 build ids on the other lines: CLOSED. I collected every id-shaped token from the lines this PR removed (7 distinct) and counted them in the head: 0 remain (HIGH, run). Hex-shaped tokens left: :252, :292, :1099 (code-history ids), :1656 (a hash prefix with ellipsis, kept by the builder and named), :949 and :2162 (a word and a SQL number, not ids) (HIGH).
- C2 workstation name at :938, :1302: not in this PR's diff, still present on this head alone; CLOSED in the merge of PR 379 with PR 342's new head 697b8ec: zero runbook lines carry the name afterwards, Windows profile paths 0, one unix home path remains (:984 on this head; counted 1 after merge) (HIGH, merge in a scratch tree). The name remains in 19 other tracked files tree-wide (not this PR's scope; C-872 C1).
- C2 dated observations: the seven named lines now carry placeholders (:54, :531, :536, :564, :1340, :1374, :1806 are no longer in the ISO-date list) (HIGH).
- C3 soaks: OPEN (objection 1). C4: OPEN (objection 3). F-C870-6 stale file:line citations: not touched, not re-checked.
- F-C870-7 PR body accuracy: not read here (PR body not checked).

## Commands against scripts
All files the runbook names that are absent from the tree: 13 names. Ten are tagged "not in this repository" or "outside this repo" at every mention (:114, :927-928, :1032, :2058, :1259, :1267, :1291); `gb10-a8-arm.sh` and `fgate_checks.py` at :928 sit in the sentence tagged on :927 (HIGH, read). Three are temporary or short names: `throttle.py` (made by the heredoc at :645-648), and two single-letter helpers. The in-repo scripts' `--base` flags were verified under C-870; I did not rerun them. I did not check the outside scripts' behaviour or flags.

## Evidence
- Diff scope (a3cc199 and 2d6a167 on main 63e91b2): the runbook (47+/47-) and tools/tests/test_deploy_docs.py (1 line). Author and committer: the no-reply Don Hagell identity on both commits (HIGH).
- Tests on the head in a scratch tree: test_deploy_docs, test_runbook_pins_c465, test_environment_doc: 86 passed (HIGH, run).
- merge-tree: clean against origin/main, against PR 342 (697b8ec), and against PR 290's head.
- Class sweep head vs base (line counts): ISO dates 18 to 9; hex tokens 17 to 6; IPv4 25 to 25 (loopback and bind addresses, unchanged by this PR; none re-judged); fly.dev 2 to 2 (ruled public); email 0; private-key marker 0; image digest 0.

## Conditions
1. Do not call the runbook scrubbed or soak-compliant until PR 290/386 and PR 342 land with it. Blocking for the "C-606 done" claim; non-blocking for merging PR 379 (it strictly reduces exposure).
2. Decide whether :484, :1093, :1636 and :1059 are scrubbed (non-blocking, Don's ruling).
3. Carry the approval-in-chat line and citation re-grounding as the docs card (non-blocking).

Not verified: CI, GX10, PR body, outside-script behaviour, every IPv4 line's nature.
