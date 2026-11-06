# Review PR 825 @c9178deb (deploy runbook scrub, C-607; delta over my PASS WITH CONDITIONS on ec97988e) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `c9178deb43d2f8843fd62e75fba47ba1022ea2ef`. My condition C1 (the leftover commit id `56d63c3` at runbook line ~1099) is MET. The one condition that remains is landing: main has moved (f7408db5) and a trial merge of this head conflicts in docs/runbooks/v1.2-deploy-rollback.md (other PRs now edit the same file: the G22 gates, G20 phase 2 and others). It needs a rebase with the conflict resolved append-style, and a re-run of test_deploy_docs and the anchors check after it. Plus the standard light CI (docs only).

## Checks (HIGH, run by me)
- Delta ec97988e..c9178deb: one file, one line: "written against `56d63c3` plus PR #32" -> "written against `<build-id>` plus PR #32". Identity: 6 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 6; trailers Sonnet 5.5; .github/: 0 files.
- Residual scan of the head's runbook: `56d63c3` 0 hits; `rog-command`, `donal`, `C:\Users`, `claude-session-scripts`, `8628814`, `1c14b52`, `db5ad33`, `fd01623`, `ee64fb9`, `98e56f6`, `1403fba4`, `f262a738`: 0 hits. The only hex tokens of 7 to 12 characters left are `31622400` (a number in a SQL line) and `3a068358` in row T4 of the identity table ("GB10 vt-renewal cron ... pinned 1.5, sha256 `3a068358...`"): a FILE hash prefix of a pinned estate script, not a commit or build id, and already on main before this PR (1 hit on main). It reads as an estate fact in a public file (LOW; outside this PR's scope; the coordinator may want it scrubbed in a later card).
- Tests on the exact head (Windows): test_deploy_docs, test_docs_no_line_cites_sd1, test_environment_doc and test_runbook_pins_c465 together 107 passed; `environment_anchors --check` 0 wrong rows.
- The reversal checks from my first review still stand (no test pins the scrub or the approval wording; unchanged by this one-line delta), so the optional follow-up lint I proposed is still the way to keep the scrub from regressing.

## Not verified
CI; the trial merge's actual resolution (conflicts exist; I did not resolve them); whether main's new runbook text adds anything the scrub should cover.
