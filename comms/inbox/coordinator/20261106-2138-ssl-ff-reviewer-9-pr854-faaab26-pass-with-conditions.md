VERDICT: PASS WITH CONDITIONS on faaab269049cbd71134b8c47db40bc394f2e16ca  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). One MEDIUM (a test that cannot fail), one LOW test gap, runbook claims partly unpinned.

R-PR854-faaab26, PR 854 (S2-4 / red-team R-1: kill-switch tests for a revoked or unreadable kill-switch identity under REQUIRE, plus a Stage 2 rehearsal script). Applies to this head only. gh pr view 854 confirms the live head; base 250154d3 = main, 0 behind, `git merge-tree` clean.

OBJECTIONS FIRST
1. test_the_refusal_is_visible_on_health cannot fail. Its assertion is `json.dumps(h).lower().count("refus") >= 1 or h.get("operator_refused_count", 0) >= 1`: any /health body with a field named like `refused_count` already contains "refus". Proof: with the kill POST removed from the test (my mutant H1) all 8 tests still pass, and with the whole body replaced by `pass` (H2) they still pass. The PR body item 3 and runbook step 4 ("refused_count rising") are therefore not pinned by this file. MEDIUM. HIGH confidence (measured).
2. "Fail closed" is the PR's word for a result that is worse than it sounds for a KILL switch: with the kill-switch identity revoked, a kill answers 502, nothing is flipped and, in code, no halt signal is sent either (api.py `_kill_one`: the registry flip at lines 596 to 598 raises before the signal block; the signal is "sent even on an idempotent re-kill" only after a successful or already-killed record). So the agent KEEPS RUNNING; the control is loud (502) not effective. The runbook covers it (step 5 B-7, then "halt the canary's process with B-1"), and the tests pin the 502 and the unchanged record, which is what the card asked. Not a defect of the PR; a reader of "fail closed" should know the agent stays live until B-7 or B-1. MEDIUM-LOW on wording, HIGH on the code reading.
3. The negative half of the break-glass rule is not pinned here: my mutant R2 (the registry honours `x-field-operator-on-behalf-of` for ANY authenticated caller, not only one holding bypass_operator_list) SURVIVES this file (8 passed). The file tests that the bypass identity must name an operator (403 without it, 200 with) but never that a non-bypass identity naming one is ignored. It may be pinned by older tests (test_on_behalf_of_c12_*), which I did not run. LOW.
4. Runbook step 3 says the 502 body starts `registry unreachable — cannot kill: registry returned 401 or 403`; the tests assert only that "registry" appears in the detail (and 500 or 502 for a drill). The exact wording, and step 4's "no kill.* row is written for the refused attempts", are asserted nowhere (the tests check only that registry.status_changed is empty). LOW.
5. In the parametrized OFF/LOG-ONLY test the "off" case never revokes the kill-switch key (the revoke is inside `if mode == "log-only"`), so it proves OFF answers 200, not that a revoked key changes nothing in OFF. LOW.
6. The B-7 test pins the human path (Don's own key flips the record, ledger names `don`); the card text said the kill with break-glass headers succeeds, and the author documented why that is not testable (a broken kill-switch identity). Accepted. HIGH.

ASSUMPTIONS
A1 The card is the author's description; I judged the file against the PR body and the runbook text, not the card (not read).

REASONING / CHECKS
1. Diff read: one new test file +192 and a runbook insertion +17 (Stage 2 step 8 rehearsal R-1); no service code touched; nothing under .github/. The runbook text names no estate address, no flag value and no build id; it uses `$PGC` and `<...>` style references and states "canary only, with the deployer". HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src of kill-switch, agent-registry, sealed-ledger and field-core on PYTHONPATH): the new file 8 passed, 0 failed. I did not run the full kill-switch suite. HIGH.
4. Mutants on a copy of the head (the new file only, -x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| K1 | kill: a registry error on the flip is swallowed (fail open) | KILLED |
| K2 | revive: a registry error on the flip is swallowed | KILLED |
| K4 | kill flip error answers 503 instead of 502 | KILLED |
| K5 | revive flip error answers 503 instead of 502 | KILLED |
| R1 | registry: on_behalf_of never honoured (break-glass refused) | KILLED |
| R2 | registry: on_behalf_of honoured for any authenticated caller | SURVIVED (objection 3) |
| H1 | health test with no kill posted | SURVIVED (objection 1) |
| H2 | health test body replaced by `pass` | SURVIVED (objection 1) |

Counted from the table: 8 run, 5 KILLED, 3 SURVIVED, 0 NOT APPLIED. A ninth edit of mine (K3, "the 502 text says revive") was a no-op and is not counted. H1 and H2 are mutations of the test file itself: they show the health test is vacuous; they are not product mutants. Of 6 product mutants (K1, K2, K4, K5, R1, R2), 5 killed, 1 survived. Per behaviour: kill/revive fail-closed 4, break-glass 2, health 0 (vacuous). The PR body's four mutants (kill swallowed, revive swallowed, on_behalf_of ignored, `named = True` without binding) I did not repeat except the first three. HIGH on the counts.

CONDITIONS
C1 (required, small; a condition fix on the head) make the health test real: assert the registry /health refusal counter is greater after the refused kill than before it (read it before, read it after), and drop the string-count escape; then H1 and H2 die. The runbook's refused_count claim then has a pin.
C2 (non-blocking) add the negative on-behalf-of case (a non-bypass identity sending the header is ignored) so R2 dies, or cite the older test that already does; assert the exact 502 wording and that no kill.* row exists after the refused attempts.
C3 (non-blocking) call the behaviour what it is in the docstring and runbook: the kill FAILS (502, the agent keeps running) until B-7 or B-1; the word "fail closed" describes only the unchanged record.
C4 (standing gate) GX10 16/16 on this exact head; CI on this head; not run by me.

NOT VERIFIED
The full kill-switch suite, CI, GX10, the older on-behalf-of tests (for R2), the runbook rehearsal on an estate (deployer work).

CONCLUSION
The tests do pin the central claim (a revoked or missing kill-switch identity makes kill and revive 502 with the record unchanged, and break-glass and Don's key work) and 5 of 6 product mutants die. One of the eight tests, the health one, cannot fail and so does not back the runbook's health claim. PASS WITH CONDITIONS: C1 is a small required fix, C2 and C3 are optional, C4 the gate.
