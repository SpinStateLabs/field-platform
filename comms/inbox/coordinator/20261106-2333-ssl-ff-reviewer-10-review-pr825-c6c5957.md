# Review PR #825 (deploy runbook scrub, C-607) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `c6c59571e88e0064a32caad01d29559f464f4dec`. One docs condition (C1: the scrub is called finished but some items of the same class remain). This head is the follow-up to ssl-ff-reviewer-7's PASS WITH CONDITIONS on `c9178deb` (comms/inbox/coordinator/20261106-1931-ssl-ff-reviewer-7-pr825-c9178de-pass-with-conditions.md), whose remaining condition (a merge with main) is met.

## Facts (HIGH, read from the head)
- 7 commits (d8096cb1, 790d9b6b, 4fd1c4a3, e4d7ba34, ec97988e, c9178deb, c6c59571 a merge of origin/main); 2 files against main: docs/runbooks/v1.2-deploy-rollback.md (+60/-56 net 114 changed lines), tools/tests/test_deploy_docs.py (the section marker string `rog-command (Windows PowerShell 5.1)` becomes `<control-workstation> (Windows PowerShell 5.1)`). Nothing under .github/.
- All seven commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is level with main: the merge base is `41afda50`, which is current `origin/main`; 0 conflict markers in the runbook.
- The reviewed diff is exactly the scrub, nothing else: I read every changed line of `git diff origin/main HEAD`. Changes: `rog-command` and the Windows profile path become `<control-workstation>` and `%USERPROFILE%`; commit and build ids (`56d63c3`, `8628814`, `1c14b52`, `db5ad33`, `98e56f6`, `fd01623`, `ee64fb9`, `1403fba4`, `f262a738`) become `<build-id>`; dated deploy observations become `<date>`, `<time>`, `<n>`; two added sentences "A deploy needs Don's approval in chat before this section; do not start without it."; "(not in this repository)" tags on scripts that live elsewhere; the section 7 heading loses "NOT armed on any estate" and reads "arming is a separate step that needs Don's approval" (nothing else in the repo quotes the old heading; I grepped); and one code citation updated to `sealed_ledger/api.py:372-400 -> operator_auth.admit_ledger_event`. The merge took main's newer text and re-applied the scrub, and I found no line of main's text dropped or altered beyond those categories.

## Verification (run by me, Windows 10, Python 3.14)
- test_deploy_docs.py, test_docs_no_line_cites_sd1.py, test_environment_doc.py and test_runbook_pins_c465.py: 107 passed (138 s). `tools/environment_anchors.py --check`: 0 wrong anchor rows.
- Residual scan of the head's runbook: `rog-command` 0, `donal` 0, `C:\Users` 0, `claude-session-scripts` 0, `@spinstatelabs` 0, private addresses (192.168.x, 10.x) 0; `fly.dev` 2 (the sandbox host name, which Don's C-561 ruling says is meant to be public).

## Condition
**C1 (LOW-MEDIUM): the scrub calls itself finished (commit ec97988e) but items of the same classes remain.** Don's C-606 ruling (comms/inbox/coordinator/20261104-2400-groomer-don-rulings.md) is "scrub home paths and the workstation name; build/release ids and dated deploy observations to placeholders". On the head:
- Home paths: `/home/spinner/...` appears 19 times (for example `/home/spinner/.field-local/keys/svc-<name>/`, `/home/spinner/field-backups/operators-staging/operators-don.json`, `KEYS=${FIELD_CALLER_KEYS_DIR:-/home/spinner/.field-local/caller-keys}`) and the account name `spinner` 25 times ("owned by spinner", "as spinner"). They were on main before; whether a GB10 account layout counts as a "home path" for this ruling is not clear from the file. Reviewer-7's and the builder's residual scans did not search for it.
- An estate file fingerprint: l.1266 `(sha256 starts c6c2c2b4cd6ccca3)` for the staged operators file (16 hex characters; reviewer-7's scan covered 7 to 12 and listed only the T4 `3a068358`).
- Dated observations: l.1068 "the 2026-10-03 move to the spinstatelabs account replaced `<volume id omitted>`" (an estate history fact), l.479 and l.482 "Grantor (corrected 2026-10-21)" and "the grantor the 2026-10-12 run used" (dated verification runs).
Fix, either way: scrub them (`/home/spinner` to a placeholder such as `<gb10-home>`, the file prefix to `<sha256-prefix>`, the three dates to `<date>`), or add one sentence to the commit message and PR body saying that the account layout and the three items are kept on purpose (and why). Without it "finished" is not accurate and the public-repo rule (no estate facts) is not met by this PR.

## Optional (LOW)
1. `<build-id>` now stands where the text named the specific pre-#32 commit: "Do NOT set `FIELD_OPERATOR_REQUIRE` on an image built from `<build-id>`" (l.~1390) no longer says which image; other lines add "any image from before PR #32", this one does not.
2. The new citation `sealed_ledger/api.py:372-400` stops two lines before the `admit_ledger_event` call at l.402; the repo's line-cite lint (SD1) passes it, but it is off by a few lines.
3. Row T4 still shows the file hash prefix `3a068358` of a pinned estate script (reviewer-7's note); the builder left it out of scope.

## Not covered
CI and the GX10 16 of 16 on this head (verifiers ran 16 of 16 on `c9178deb`: comms/inbox/coordinator/20261106-2053-ssl-ff-verifier-6-pr825-c9178de-16of16.md and 20261106-2142-ssl-ff-verifier-5-gx10-run-pr825-c9178de.md); the other docs in the repo; Linux.
