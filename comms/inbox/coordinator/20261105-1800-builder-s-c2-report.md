# Report: S-C2 (scout round 3), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or note for the sentinel governor URL.
PR 524 (draft): https://github.com/SpinStateLabs/field-platform/pull/524, branch fix/sentinel-governor-url-quote-sc2, head d299153550f10c166083140850a5e4f0e5b3de31 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: sentinel).
Hardening (R, 11 red tests): SpendStatusClient.status/totals_since put the agent id unquoted in the governor path; httpx collapsed a/../../caps/victim to /caps/victim, split a?x=1 into a query, dropped a#frag's tail. The sentinel reads spend status to decide ALLOW/ESCALATE. Fix: _seg (ops-console's rule), used for /status/{id} and /totals/{id}; plain slugs byte-identical. Helper defined at the END of engine.py with its import inside so the env-read line numbers cited by docs/ENVIRONMENT.md do not move (anchors --check 0 wrong with no docs change).
23 tests; sentinel 286 passed; boundary-echo/proxy-lint/env-doc tools tests 225 passed; one mutant 5 red.
Not done: the same unquoted pattern in field-core clients.py (~377-378, 427-431 per the scout, not re-read): a separate, wider card (it touches every service). Exploitability unproven (whether a crafted id passes the earlier registry lookup).
Overlap: PR 517 (sentinel governed.py) and origin/feat/c1180-... touch the same service; textual conflicts not checked.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518, 519, 521, 522, 523, 524; none merged by me.
Round 3 not yet taken: S-C8 (overlaps origin/feat/c1179-spend-governor-cli-l12); docs/CI S-D1..D8.
Proposal for a new card: field-core clients.py unquoted ids (LedgerClient/RegistryClient/others), one sweep with the ops-console P-4 quoting sweep.
