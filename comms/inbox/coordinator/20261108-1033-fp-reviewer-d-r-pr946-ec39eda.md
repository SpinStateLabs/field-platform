# Review R-PR946-ec39eda
**VERDICT: PASS** on head ec39eda840c0a75dc9ae44c54351cdf7a49ed7a0 (fp-reviewer-d)

Independent: one commit authored/committed by Don Hagell; I did not write it.

## Objections first (FORCE)
1. Thread-per-signal abandonment: a drip-fed endpoint keeps its worker thread until httpx gives up (stated in the PR body). A flood of such endpoints could hold threads; bounded in practice by the 20 s domain budget (at most ~8 signals started per domain kill) but not across repeated kills (MEDIUM). Daemon threads do not block exit (mutant D11 survived: not testable cheaply, as the PR says).
2. The new tests assert wall-clock bounds (`took < 2*2.5+1.5`). Under heavy parallel load my unmodified control failed `test_once_the_domain_budget_is_spent...` once (three other test jobs running); on a quiet machine the same control passed twice (7 passed each), and the full kill-switch suite passed 431/431 under the same load. CI-flake risk, LOW-MEDIUM; the GX10 gate should be run unloaded.
3. A domain kill whose first agents consume the 20 s budget skips signals for later agents: they are flipped to killed but never told to halt. Intended and documented (README), and the reason is ledgered as `kill.endpoint_skipped` / `budget`; the new reason strings (`timeout`, `budget`) are flagged in the PR body as Don's decision (not in source whether approved).

## Checks
- Head confirmed ec39eda840c0 = PR head at start and end (HIGH). Author AND committer Don Hagell 13129187+dhagell noreply (HIGH).
- Files: docs/ENVIRONMENT.md (1 cell), kill-switch README, api.py (+54-11), tests (+150). Nothing under .github/; no secrets or estate addresses in the diff (only 127.0.0.1 test sockets) (HIGH).
- Doc cite: ENVIRONMENT.md moves the FIELD_KILL_ENDPOINT_ALLOWLIST cite to api.py:316; on the head, api.py:316 is the `os.environ.get("FIELD_KILL_ENDPOINT_ALLOWLIST", "")` line (HIGH). `t0` in kill_domain is set at api.py:722 before the loop, so the budget measures the whole domain call (HIGH).
- Merge with current main: clean (`git merge-tree`). Merge with PR 944 (9c5c905): CONFLICT in docs/ENVIRONMENT.md only (the same cite row: 944 sets :308, 946 sets :316; README and api.py auto-merge). Whichever lands second must re-cut that row (`environment_anchors.py --fix`) — mechanical; not a condition on this head.
- kill-switch full suite on the head: 431 passed (HIGH).
- Repo-wide tools/tests on the head: 13 failed, 4405 passed, 27 skipped; failing ids IDENTICAL to the 13 failing on main (sorted-id diff empty); the ENVIRONMENT anchor and C-57 lints pass (HIGH).

## Mutants (scratch copy of api.py, never the PR branch; set = the 7 new tests in test_endpoint_and_liveness.py, `-x`; control 7 passed on a quiet machine, twice)
Rows marked (q) were re-run on a quiet machine after the loaded control failed once; their result is the quiet one.
| id | behaviour | mutation | result |
|---|---|---|---|
| D1 | deadline < budget < 30 | deadline 30.0 | killed (constants-ordered test) |
| D2 | wall-clock deadline | `join()` without timeout | killed (drip test) |
| D3 | timeout reason | reason transport_error | killed |
| D4 | timeout outcome | outcome skipped | killed |
| D5 | budget skips (q) | threshold 1e9 (never skips) | killed |
| D6 | budget not always | threshold 0 (always skips) | killed |
| D7 | budget reason (q) | reason "x" | killed |
| D8 | budget outcome (q) | outcome failed | killed |
| D9 | worker exceptions kept (q) | exception swallowed, returns None | killed (transport_error test) |
| D10 | budget under 30 s | budget 40.0 | killed |
| D11 | daemon worker (q) | daemon=False | survived (no cheap test, as disclosed) |
| D12 | skip flag passed (q) | skip_signal not passed to the signal | killed |
| D13 | skip honoured (q) | `if skip_signal` off | killed |
| D15 | deadline branch | `is_alive` check off | killed |
| D16 | timeout < deadline | deadline 2.0 | killed (constants-ordered test) |
| D17 | single kill unchanged (q) | skip_signal defaults True | killed |

Totals counted from the table: applied 16, killed 15, survived 1 (D11), not applied 0 (two first-pass patterns for D12 and D17 did not apply; fixed and re-run, counted once each).
Source: own run 2026-11-08, Windows venv, PYTHONUTF8=1, relative PYTHONPATH.

## Conditions
None.

## Optional LOWs (new PR, not on this head)
- Loosen or fake-clock the wall-clock asserts to remove the load flake (objection 2).
- Coordinator: land 944 before 946 (or the reverse) and re-cut the ENVIRONMENT.md cite row on the second.
