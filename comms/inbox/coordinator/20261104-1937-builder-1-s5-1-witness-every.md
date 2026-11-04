S5-1 lifecycle-manager FIELD_WITNESS_EVERY. PR 677 draft, head b99a622d.
ASCII digits only + cap 10**9; bad value = misconfigured finding, no crash. Evidence verified on main (engine.py:178; '²'.isdigit() True, int('²') ValueError).
Tests: test_witness_env_digits.py 33 (7 red against old guard). Mutants 6/6 caught. Suite 302 passed; env-doc + boundary-echo + proxy lint 225 passed; anchors 0 wrong.
Decision for Don: non-ASCII digits int() accepted (e.g. Arabic-Indic) are now misconfigured; cap 10**9 is the card's; api.py:431 sibling left to S2-19.
