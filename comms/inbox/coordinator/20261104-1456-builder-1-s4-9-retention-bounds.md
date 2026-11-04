# builder-1 S4-9 (sealed-ledger retention apply bounds, HIGH CARE)
PR: https://github.com/SpinStateLabs/field-platform/pull/657 (draft), head 7814e513.
Ran: tests/test_retention_apply_bounds.py 14 (10 red before, 4 controls); 7 mutants all caught (5, 1, 1, 2, 2, 2, 1 failed, incl. cutoff-placement and path-echo); services/sealed-ledger/tests 816 passed, 5 skipped, 1 error = test_operator_observer_c6_serve (errors on unmodified main in this sandbox).
Archive semantics unchanged: days=0 still archives [1, 2] and the ledger verifies (tested). Only changes: days bound 0..36500 (API le, CLI one-line refusal exit 2, store ValueError), cutoff computed before mkdir, NUL archive_dir -> ArchiveRefused (fixed text).
Decision for Don: 36500 is the card's suggestion. Needs a second reviewer (HIGH CARE). PR 522 fixes the same NUL class on /export; different lines as far as I read.
