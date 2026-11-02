# Claim: C-1182 (Lane R, rebase builder). HIGH CARE.

Claiming C-1182 (pair-bearing field-core clients leave trust_env at the httpx default). Checked on main 6385f877: `packages/field-core/src/field_core/clients.py` lines 290 and 373 build `httpx.Client(timeout=5.0)` with no trust_env, so the premise holds (HIGH, read). `git grep -l -w C-1182 -- comms/inbox/coordinator` found nothing before this claim.

Note on the card text: the source note 20261102-2130-reviewer-c1150.md labels a different item F5 (the lifecycle CLI ledger table). The card describes the clients.py finding; I work the card as written and do not touch the lifecycle CLI (C-1171 rebuild).

Plan: fresh worktree on main, fail-first test (proxy variable set, no request goes through the proxy) for both clients, set trust_env=False on both, run the C-57 proxy-lint tests and the field-core suite, update the allowlist only with a named reason, mutation check, draft PR. Noreply identity. I will report with the full head sha.

Read, not measured.
