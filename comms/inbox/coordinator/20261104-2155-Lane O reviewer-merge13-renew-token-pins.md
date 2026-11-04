# LANE O post-merge review (completes part of my MERGE 13 report): tools/tests/test_renew_token_pins_c212.py and tools/renew_token.py pins @ 32b6eaa3

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Read-only mutant review, at the merged tip 32b6eaa3 (rb-stack2, MERGE 13), of the part my earlier MERGE 13 report left uncovered: the `renew_token` pins (token record fields, renewal-window boundaries, `is_guarded`, the operator header on mint and revoke only, the escaped secret form). `git fetch origin main` first; neither tools/renew_token.py nor the pins file changed on main after 32b6eaa3 (`git log 32b6eaa3..origin/main` on both is empty). The commits that built the pins file are Don Hagell numeric noreply (read from `git log`; checked 33988335 and the file's history at 32b6eaa3). Still NOT covered from MERGE 13: the body-drain test change and the ENVIRONMENT.md rows ("I do not know").

Objections first: (1) the pins test a 1,600-line tool through nine small functions; a mutant in `Renewal`'s state machine (journal, lock, store) is out of this file's reach and I did not mutate it. (2) The renewal-window message is pinned fully for "expired" (`expired 3.0 days ago`) but only by `startswith("expires within 7 days")` for the window case. (3) The secret-form pins hold the escaped text of one string, not the printed shape of a real traceback beyond the two samples.

Baseline (unmutated, measured): the three renew_token test files (test_renew_token_pins_c212, test_renew_token, test_renew_token_ledger_helpers_c1042) 253 passed in 110 s. Survivor check ran the two older files (test_renew_token.py and test_renew_token_ledger_helpers_c1042.py), not the whole tools suite (too slow per survivor).

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 token record: one refusal per field, and it names the field | 10 | 10 | 0 | 0 |
| B2 renewal window: exactly 0 is expired, exactly the window renews, text exact | 8 | 7 | 0 | 1 |
| B3 is_guarded: whole path, exact method, query ignored, id segment non-empty | 8 | 8 | 0 | 0 |
| B4 the operator pair rides the mint and the revoke only | 4 | 4 | 0 | 0 |
| B5 secret forms: the verbatim secret and the repr body | 4 | 4 | 0 | 0 |
| Total | 34 | 33 | 0 | 1 |

Totals counted from the table: 34 = 33+0+1; no invalid, no noapply.

Survivor (real gap): B2 `{left:.2f}` instead of `{left:.1f}` in "expires within N days: X days left": the digits after the decimal point of the in-window message are unpinned (the test asserts `startswith` only).

Conditions: none blocking. Optional: assert the full "expires within 7 days: 7.0 days left" string. Confidence: HIGH on counts, MEDIUM on completeness (nine functions only). Token/cost: I do not know.
