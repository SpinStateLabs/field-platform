# Claim and report: scout P-1 (not yet numbered), builder. UNVERIFIED (cloud, no GX10).
Claim check (done before building): every OPEN builder card C-1180..C-1206 has a comms note and/or a remote branch (list: C-1180, 1181, 1183, 1184, 1186, 1187 (Lane O released, branch exists), 1190, 1191, 1192, 1196 (PR 481), 1197, 1198, 1203, 1204, 1205, 1206; C-1199 stays with Lane 13 per STATUS; C-1188 waits for the 368+380 batch). BACKLOG: B-11 covered by PR 414, B-18 already pinned on main (test_http_env_proxy_lint_c57.py C-494 alias cases), B-19 blocked on C-511, B-22 GX10 only. So I took the next unclaimed scout proposal. Please number it.
PR 489 (draft, main): https://github.com/SpinStateLabs/field-platform/pull/489
Branch fix/sweep-unparseable-ts-p1, head 53c30a02f0caea0fa2ef529c35717fa73bfdc5e9 (one commit on main cd3b7690, noreply identity). Reviewer needed (not this author).
Evidence on main: holds. Bug: failing test first (9 red for the stated reasons), minimal fix in engine.py (+ optional SweepReport.unreadable_timestamps, record id and field name only; markdown section only when non-empty). api.py and cli.py unchanged (pass-through).
Ran: lifecycle-manager suite 279 passed (typer installed into this env; all services' src on a relative PYTHONPATH); one mutant (unguarded token parse restored): 3 red, restored.
Not run: GX10, 16 suites, other services. Did not read every caller of sweep for an outer except.
Open for Don: P-1 chose "skip and name" over "fail the sweep"; the field is additive. Also earlier: PR 488 (P-6) awaiting CI/review.
