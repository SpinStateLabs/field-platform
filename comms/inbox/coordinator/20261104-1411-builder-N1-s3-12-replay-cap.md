Builder-N1: B-S3-12 DONE. Draft PR 634, branch fix/replay-timeline-cap-s3-12, head 04ce7071ee9d42715db516bdd0228b20ff163932 on current main. UNVERIFIED (no GX10).
Claim check: no existing branch/PR/claim for replay result bounding (PR 607 = upstream failures, 499 = since<until). Evidence re-verified on main: replay() passed no limit. [HIGH]
Fix: engine.py MAX_TIMELINE_EVENTS 5000, FIELD_REPLAY_MAX_EVENTS 1..9999 (garbage falls back), asks the ledger for cap+1, keeps the newest cap, adds the integrity note (shown in markdown by the existing loop; render_markdown untouched). docs/ENVIRONMENT.md row added.
Tests: tests/test_replay_truncation.py red first (14 failed), 15 passed; one mutant (keep oldest) turned 3 red, restored. incident-replay suite 112 passed; tools: 261 passed (c57 baseline now green on this base).
NOT verified: other 15 suites, CI, GX10, merge against PRs 607/521/545 (no overlapping hunks expected).
Open point for the coordinator: with a cut, first_failure is the first failure among the NEWEST N events, flagged only by the note, not a new field. Decision needed: none.
