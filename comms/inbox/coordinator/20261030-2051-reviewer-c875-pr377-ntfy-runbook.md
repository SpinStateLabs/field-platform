VERDICT: PASS WITH CONDITIONS on dfceabcfc3bbcd7cc81a602dd1fcff23e79869b7  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-875, PR 377 (docs: the ntfy runbook states what main sends today, a test alert only). One commit, one file: docs/runbooks/ntfy-alerts.md (+21 -14). Checked against origin/main (63e91b2, which equals the PR's merge base for alerts.py and cli.py). Public-safety class: no value of a topic, token, host or personal path is printed here. This SHA only.

OBJECTIONS FIRST
1. Two line citations in the new text are off. The runbook says the production classes are defined at `alerts.py:127-160` and the sender command at `cli.py:150-166`. On main the CLASSES dictionary runs 130-161 (the six production entries end at line 155 and the `test` entry is 156-160; line 127 is the comment above it), and the `alert-test` command runs 150-172 (the exit line is 172). The 127-160 range also includes the test class, so "the six production classes ... (alerts.py:127-160)" is loosely worded. The `health_fields` cite `alerts.py:235` is exact. Confidence HIGH. LOW, cosmetic; a pinned test of the cites would be needed to keep them true.
2. The central claim is TRUE on main: the only caller of the sender is the `field alert-test` command (cli.py:163 calls `alerts.send_test`); `alerts.send` has no caller outside the library, the CLI and the tests; no service merges `field_core.alerts.health_fields()` into `GET /health`. Evidence: repository grep of main outside tests and docs for `alerts.send`, `field_core.alerts`, `from field_core import alerts`, `send_test`, `health_fields`: the only non-library hits are the CLI (cli.py:161-164, 182) and the operator-health `health_fields` of each service, which is a different function (operator_health.py:279 and the services' api.py lines; they do not include the alert counters). Files mentioning the alerts module on main: the library, the CLI, field-core's README and tests, docs, CHANGELOG. Confidence HIGH.
3. Table rows match the code: priorities and tags of all six classes in the runbook equal `CLASSES` (rotation_failed 5, rotation_overdue 4, breakglass_used 5, stage_transition 4, stage_aborted 5, rotation_halted 5; tags as in alerts.py:130-155). The delivery paragraph also matches: default deadline 5 s capped at 30 s (alerts.py:93-94), 3 attempts default capped at 5 (:95-96), back-off 1 s then 2 s (:98), retries on 429 and 5xx only (:472). Confidence HIGH.
4. Statements still unverifiable or loose: "The senders are deferred until the key-rotation work (PR 57) is reworked (card C-760)": C-760 is an OPEN builder card (TASK-QUEUE.md:763) whose job is to correct the docs, and the ruling that defers senders is C-552 (DECIDED); citing C-760 as the reason for deferral names the docs card, not the decision. Line 16 of the runbook ("P36 makes stage gates automatic, with one condition: alerts are live and a test ...") still reads as a present-tense precondition; it is true as a precondition and does not claim senders exist. Confidence MEDIUM.
5. Other documents on main still describe ntfy alerts as delivered without the qualification: CHANGELOG.md:24 ("ntfy push alerts with an alert-test CLI and runbook") and packages/field-core/README.md:20 and :30 describe the library and CLI accurately (they name `send`/`send_test` and the test alert command) and do not claim production senders; docs/ENVIRONMENT.md rows were not read. So no contradiction found, but C-760's wording "wherever the repository says ntfy alerts are live" was only partly searched by me (markdown files). LOW.
6. Public-safety scan of the whole file at the head: no home-directory or profile path (the two personal profile paths on the removed lines are replaced by `<home>`), no IPv4 address, no mailbox, no token-shaped string (one `tk_...` literal placeholder), no user name. URLs: `https://docs.ntfy.sh` (11), `https://ntfy.sh` (2), `https://ntfy.example.org` (1, a reserved-style example): no private server, topic or channel detail. Four long identifier-like strings are test and counter names, not topics. Confidence HIGH.
7. Tests: tools test_environment_doc.py and test_deploy_docs.py 78 passed; field-core test_alerts_ntfy.py 62 passed. No test pins the runbook's new sentences or cites. Commit: author and committer Don Hagell no-reply; no value, address or deploy status in the diff.

ASSUMPTIONS
A1 Card scope: each statement against the sender code on main at file:line; no estate-specific channel detail, secret or topic name. A2 "Main" is origin/main at 63e91b2.

REASONING / CHECKS
- Read the removed and added lines; compared each factual claim with alerts.py and cli.py on main (line numbers above); grepped main for callers; scanned the file for sensitive classes.
- Not run: any alert send (no network, no topic).

CONDITIONS
C1 (non-blocking) Correct the two line ranges (alerts.py:130-161 or "CLASSES", cli.py:150-172), or cite by name instead of line.
C2 (non-blocking) Cite C-552 (the ruling) for the deferral, with C-760 as the docs card.
C3 (non-blocking) When C-760 lands, search all file types, not only the runbook, for "live" claims.

NOT VERIFIED
GX10, CI, docs/ENVIRONMENT.md and other non-runbook text for live-alert wording beyond the markdown files I grepped, a real send.

CONCLUSION
The runbook now states what main does: one sender (the test alert command), a library with unsent production classes, no service merging the alert counters. The table and delivery figures match the code; two cites are slightly off. PASS WITH CONDITIONS, UNVERIFIED.
