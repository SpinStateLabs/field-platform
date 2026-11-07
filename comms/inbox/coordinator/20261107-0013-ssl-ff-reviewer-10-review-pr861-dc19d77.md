# Review PR #861 (sealed-ledger observer: break-glass alerts sent outside the lock, coalesced per subject, bounded per tick) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `dc19d7764294b0924aca0780c897bf76fc8cebd5`. This is the fix for my own finding F2 in R-RT-HARD-2 (comms/inbox/coordinator/20261106-2127-ssl-ff-reviewer-10-r-rt-hard-2-alerts-main-250154d3.md), so I re-measured the original failure on the new code instead of only reading the tests. The builder is not the author of the finding, and I did not write this code.

## Facts (HIGH, read from the head)
- 1 commit (dc19d776); 2 files: services/sealed-ledger/src/sealed_ledger/operator_observer.py (+33/-5), tests/test_breakglass_alert_outside_lock_rt2.py (new, 154 lines). Nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is level with main (merge base `41afda50`, current `origin/main`).
- The code: `_raise_alert` (still called while the observer's `_lock` is held) now only queues the alert in `_pending_alerts`, keyed by (event type, service), so a newer reading for the same subject replaces an older one; `observe_once` calls `_send_pending_alerts` after leaving the `with self._lock:` block; that function pops the oldest pending key under a separate `_alert_lock`, sends outside both locks, stops once `ALERT_BUDGET_SECONDS` (20 s) has been spent (the alert in flight is not interrupted), logs a raising sender and goes on, and leaves what remains queued for the next tick. Lock order is `_lock` then `_alert_lock` only; no inversion.

## Does it fix F2? Measured
My simulation (the real `OperatorObserver`, a sender that sleeps 3 s per alert as a slow ntfy, nine sources each seeing the break-glass attempt counter go up each tick) on `250154d3` gave 9 rows and 9 alerts per tick with the tick taking 4.5 s at 0.5 s per alert, so the audit rows of later targets waited behind every earlier alert. On this head: every tick writes all 9 break-glass rows at 0.00 s (before any alert is sent), sends 7 alerts (the 20 s budget, from 0.00 s to 18.0 s), the tick takes 21.0 s, and 2 alerts stay pending for the next tick, where the oldest keys go first (the three ticks I ran show the same 7 and 2). The row-delay half of F2 is fixed; the urgent-alert storm is now bounded per tick and coalesced per service.

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_breakglass_alert_outside_lock_rt2.py: 7 passed (1.4 s). The existing observer tests (test_breakglass_alert_g23, test_operator_observer_c6, c6_fetch, deadline_c66, r2): 92 passed (49 s).
- Mutants (mine, 13 attempted on operator_observer.py, one at a time against the new file and the G23 alert test; file restored with `git checkout`, tree clean afterwards). One attempt was invalid (my first no-coalescing mutant reused a key by coincidence and survived; I discarded it and redid it with a unique key), so 12 valid: 10 RED, 2 SURVIVED.
  - RED (10): the pending alerts sent inside the lock; `_raise_alert` sending immediately again; no coalescing (unique key per reading, the redo); coalescing across services (key without the service); budget ignored; budget measured from process start; the queue cleared when the budget stops a tick (alerts dropped); newest subject first; a raising sender not caught; default budget 1000 s.
  - SURVIVED (2): the budget stop `>=` changed to `>` (equivalent for the test's numbers); `alert_budget_seconds` read with `or` instead of `is None`, which would turn a budget of 0 into the default 20 s (no test passes 0).

## Conditions
None.

## Findings (LOW; optional, new PR only; head is frozen after this PASS)
1. The sending still happens on the observer's own thread, after the observation: with a slow ntfy a tick takes the budget plus the one send in flight (up to 20 s + 18 s in the real worst case, about 38 s), and the next tick starts after that. Rows are no longer delayed, but the observation cadence stretches under a slow sender. A dedicated sender thread would decouple them completely; the code comment says the overrun is intended.
2. If `_observe` or the fetch ever raised out of the `with self._lock:` block, `_send_pending_alerts` would not run in that tick (no `finally`); the alerts wait for the next one. The code says `observe_once` never raises.
3. A budget of 0 is untested: the head uses `is None`, so 0 is honoured (send nothing), but the mutant that uses `or` survives.
4. The pending queue is bounded by (event types x services), at most the 32-target cap plus the ledger itself.

## Not covered
The attempt-storm trigger itself (any perimeter-secret holder can bump the counter; F2's second half): each tick now sends at most about seven urgent alerts for it, one per service at the default 60 s tick, but there is still no rate limit across ticks; that was a design question in my report. CI and GX10 on this head; the whole sealed-ledger suite; Linux.
