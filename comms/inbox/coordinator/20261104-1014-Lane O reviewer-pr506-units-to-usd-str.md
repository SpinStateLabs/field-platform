# Lane O reviewer: PR 506 (scout P-5, field-core: units_to_usd_str shows every unit below one cent) @f0c3d17093de58f1fec12f43f9d643b1b6dcff40. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head f0c3d170. Lane A (field-core). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); pricing.py +8/-2, a +54-line test file. Financial display code, so I checked each figure by running it. I did not write the head. Claimed through dispatch.sh (R-PR506-f0c3d17).

Objections first: (1) the helper is now inconsistent across sign: a POSITIVE amount of one cent or more is floored to whole cents, a NEGATIVE amount of the same size is not. Run on the head (HIGH): `units_to_usd_str(1_999_999)` is "$0.19" (floored), `units_to_usd_str(-1_999_999)` is "$-0.1999999" (full precision), `units_to_usd_str(-10_000_001)` is "$-1.0000001" while `10_000_001` gives "$1.00"; a negative amount of 3 dollars shows "$-0.3" style with the sign after the dollar sign and no trailing "00". The PR says "negatives" are covered; the test pins three negative cases, none of one cent or more except -2_000_000 ("$-0.2"), so the asymmetry is pinned as correct by accident (test_a_negative_amount_keeps_its_sign_and_every_unit). (2) the one-cent-and-over branch FLOORS (1_999_999 units shows "$0.19", understating by almost a cent); the PR calls this unchanged and display only, and says nothing here is used in a cap comparison (pricing.py); I confirmed the helper is used only for display strings in spend-governor/src/spend_governor/api.py:262 (token_cost_display) and :584 (total_cost_display) (grep, HIGH). (3) sub-cent values are now seven-decimal strings ("$0.0000001"), a visible API change to those two response fields (read, HIGH).

Run here (cloud, scratch worktree on f0c3d170, relative PYTHONPATH): new file 17 passed; whole field-core suite 1561 passed, 2 skipped; the whole spend-governor suite (the only consumer) passes on this head (command output below).

Mutants on pricing.py units_to_usd_str (23 run in a scratch worktree; each against the new test file; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 below one cent shows every unit by integer arithmetic (float .6f and .7f, digits 6 and 8, strip variants, no zero padding) | 7 | 7 | 0 |
| B2 one cent and over is floored to whole cents, unchanged | 5 | 4 | 1 |
| B3 a negative amount keeps its sign and every unit | 4 | 4 | 0 |
| B4 a sub-cent amount is never shown as a whole cent | 3 | 3 | 0 |
| B5 zero shows as "$0" | 4 | 4 | 0 |
| Total (counted from the rows) | 23 | 22 | 1 |
B4 has 3 mutants (under the 4 asked).

Survivor (1, equivalent): `units > CENT_UNITS` instead of `>=`: exactly one cent then takes the sub-cent branch and prints "$0.01", the same string (read and run by the mutant, HIGH).

CONDITIONS (blocking): C1 CI green and a GX10 run of the field-core and spend-governor suites on the exact head rebased on current main (code PR; I could not run the GX10; the local suites above pass). C2 objection 1 named: either make negative amounts of one cent or more follow the same flooring and "$-" format as positives, or record that negatives are a display of exact units by design; add a test with a negative amount above one cent either way.
Optional, NEW PR only after the head is frozen: the sign-before-dollar format ("-$0.20").

Tokens/cost line: not available to me. I do not know.
