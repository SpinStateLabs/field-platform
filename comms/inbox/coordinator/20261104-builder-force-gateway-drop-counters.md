Builder report: force-gateway drop counters. PR 558 (draft), branch fix/force-gateway-drop-counters-c9c, head 00e18c239225b99c3b80535b5c5404ad8e6deac5. UNVERIFIED (no GX10).

Claim check: no existing claim, PR or branch for force-gateway ledger/spend drops (BACKLOG and inbox grep, ls-remote). Evidence re-verified on main 97dcfec1: `_ledger_event` and `_meter_usage` (the spend forwarding, /usage then /spend fallback) both ended in `except Exception: pass`. [HIGH]

Done: both counters on app.state, warning log with exception type only, both in /health, README row, docs/ENVIRONMENT.md anchors re-pointed. New tests/test_ledger_spend_drops_counted_c9c.py: red first (6 failed), then 7 passed; one mutant (spend counter increment -> pass) turned 2 red, restored.

Ran: force-gateway suite minus test_f1_enforce: 415 passed, 2 failed (test_f1_flags, same two fail on clean main), 1 skipped. environment_anchors --check: 0 wrong. The four tools tests: 260 passed, 1 failed (known c57 baseline).
NOT verified: test_f1_enforce.py (agent_registry missing here); other 15 suites; CI; Python 3.11/3.12.
Left alone: three other `except Exception: pass` in the hygiene-judge path (api.py ~674-703); not in the card, say if wanted.
Decisions needed: none.
