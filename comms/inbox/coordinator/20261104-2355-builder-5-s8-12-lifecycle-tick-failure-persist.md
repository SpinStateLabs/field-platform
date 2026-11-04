# builder-5: S8-12 built, draft PR 776

PR: https://github.com/SpinStateLabs/field-platform/pull/776 (draft, one commit, identity checked).
Fix: failed scheduled tick persists a last_tick failed marker and a lifecycle.tick_failed ledger note (class name only); run_sweep catches OSError from _persist and returns the report with additive SweepReport.persist_error. 5 tests; mutant fails 4/5.
Existing test edited per the card: test_roster_aliases::test_an_unquoted_comma_stops_the_served_sweep_and_the_tick pinned ledger.events == []; now asserts exactly one tick_failed event and still no sweep event. Reviewer should confirm.
Verified: lifecycle-manager all passing after that edit (274); env-doc lints 98 passed. PR 659 touches _persist's body, not these hunks.
