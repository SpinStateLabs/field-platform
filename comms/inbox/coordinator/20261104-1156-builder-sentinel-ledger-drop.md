Builder report: conformance-sentinel ledger-drop counter (draft PR 559)

Head: 767b35a83e0b7e8cd371f57e4b4fe57d21f71213, branch fix/sentinel-ledger-drop-counter-sc9b. UNVERIFIED (no GX10).
Claim check: no comms/BACKLOG or inbox claim, no open PR or branch for the topic (open sentinel PRs 467, 504, 517, 524, 531, 535, 544 are other cards). Re-verified on main: the three `except Exception: pass` (log-only shadow, sentinel.judge, sentinel.metering_gap) existed.
Done: `SentinelEngine._note_drop` (counter `ledger_appends_dropped`, warning with exception type only), `/health` carries the counter; verdicts unchanged. README LIMITS and ARCHITECTURE sentinel row updated.
Ran: new tests/test_ledger_drop_counter_sc9b.py red first (KeyError), green after; one mutant (judge drop not counted) red, restored; sentinel suite 249 passed with PYTHONPATH of all package/service src; environment_anchors --check 0 wrong (no ENVIRONMENT.md row shifted); lint/doc tests 260 passed, 1 failed = known baseline c57 allowlist (PR 543).
Not verified: tests/test_mode_message_c377.py (typer missing here; same on clean main); GX10 full suites; textual conflicts with open PRs 467/504/517/524 on engine.py/api.py.
Not covered: the existing metering_gap ledger payload still carries str(exc) (up to 300 chars), a ledger value, not a log; left as is.
Decisions needed: none.
