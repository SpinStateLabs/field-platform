# builder-1 S4-4 (kill-switch API hardening)
PR: https://github.com/SpinStateLabs/field-platform/pull/652 (draft), head 9da93cd6.
Ran: tests/test_kill_request_and_allowlist_hardening.py 72 (62 red before); 6 mutants caught (41, 8, 5, 3, 5, 1 failed incl. an off-by-one on the 128 bound); services/kill-switch/tests 342 passed (incl. c1189 no-echo guard).
Decision for Don: limits are the card's suggestions (operator 200, reason 1000, heartbeat id 128); automation that sends blank/long values now gets 422.
Other: #586 and #600 (never commented) got their one comment for the main-side lint (fixed on main, b963407a); #582 and #591 repeats.
