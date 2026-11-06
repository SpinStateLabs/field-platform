# RED TEAM: addendum, main ccab2379 (authn fix, controller irreversibility notice). ssl-fp-red-team, 2026-11-06
Verdicts of 20261106-1700 stand: Stage 2 NO-BLOCKER for code, conditional on PR 827 (f129b1e9, now behind main; merge main first, code unchanged) merging; Stage 3 no code blocker.
- N-2 FIXED on main (3cb0d881): non-ASCII `x-field-auth` (one byte, 120 bytes, empty, secret-plus-non-ASCII) now answers 401 on /kill and 200 on /health; was 500. Probe on kill-switch app (HIGH). 175 tests passed (authn, controller, kill-switch operator suite).
- b77408cb: the Stage 3 plan prints the irreversibility notice (image rollback unavailable; remove FIELD_OPERATOR_REQUIRE first). Controller tests pass. R1-R4 defaults unchanged (not re-tested beyond the suite).
- Residual (LOW): a header byte string whose latin-1 bytes equal the UTF-8 bytes of a non-ASCII configured secret matches by design (documented in `secret_matches`); an ASCII secret is unaffected.
- Not on main: G22 (PRs 818/827). Operator-auth, kill-switch and registry code unchanged since my last run apart from authn.
