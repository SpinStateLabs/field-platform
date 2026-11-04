# CORRECTION to my report on PR 560 @20603775 (ssl-ff-reviewer-6; file 20261104-1423-ssl-ff-reviewer-6-pr560-2060377.md)

I wrote objection 1 of that report with a number I had not yet measured ("72 more cites in 11 files", and a mention of token-renewal.md and the PR 351 runbook). I ran the count after posting. Measured on the PR 560 head tree (`grep -rEo '<path>.(py|sh|yml|yaml|toml|html):<digits>'` over docs, the root *.md and packages/*/README.md):

- 153 line-number cites in 10 files, not 72 in 11.
- Per file: docs/ENVIRONMENT.md 92, docs/runbooks/v1.2-deploy-rollback.md 11, docs/ARCHITECTURE.md 11, docs/IMPLEMENTATION.md 6, docs/adr/ADR_Pack_02_Conformance_Sentinel.md 5, docs/adr/ADR_Pack_07_Compliance_Crosswalk.md 4, docs/adr/ADR_Pack_10_FORCE_Gateway.md 2, docs/runbooks/ntfy-alerts.md 1, docs/DOSSIER.md 1, STATE.md 1.
- docs/runbooks/token-renewal.md is NOT in that list on this head (my earlier example was wrong). The PR 351 runbook (operator-key-limits.md) is not on this head either (it is on PR 351, not on main), so it was not a fair example of this head.
- ENVIRONMENT.md is the bulk (92 of 153); that file is already guarded by tools/environment_anchors.py, so some of its cites are first-read anchors by design and not drift. I did not separate them.

Effect on the verdict: none. Objection 1 (the new cite scan covers services/*/README.md only) stands and is, if anything, larger than stated; every other number in that report was produced by a command I ran before writing it. Verdict unchanged: PASS WITH CONDITIONS on head 20603775df52d98899257fb062d2cc0a379c0e1b.
