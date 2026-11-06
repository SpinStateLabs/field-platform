# Review PR 714 (attestation-reporter: a wrong-typed token_id no longer crashes the pack; S6-12) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `4efed9cdc3a236095aea5c29081e9fd6da124faf` (no conditions beyond the standard CI and GX10 on the landed head).

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. 2 files: attestation_reporter/engine.py (+4/-2), tests/test_sweep_rows_wrong_typed_keys.py (+122). Based on ebb027a2; main is 250154d3; a trial merge into current main is clean.
- Code read: in `_sweep_rows`, the key of each event is kept only when it is a `str`; anything else (a list, dict, int, bool a caller wrote into a `lifecycle.*` payload) is counted as "without <key>" and never enters the distinct set (it was unhashable, so `PackEngine.build()` raised `TypeError` and `/pack` answered 500). A non-dict `payload` is read as having no key. The change covers both the `token_id` row and the `agent_id` row. Public behaviour for string keys is unchanged.
- Tests on the exact head (Windows): the new file 12 passed (the PR said 7; the second commit added the raw non-dict payload cases); attestation-reporter tests selected by `sweep or lifecycle or retention or pack` 55 passed. The full 307-test suite takes about 12 minutes here and I did not repeat it for this two-line change (the previous head's full run was green in my PR 833 review).
- A key that is a string stays a key, including the empty string (pre-existing; see survivor K5).

## Mutants (9 attempted, counted from the table)
| # | mutant | result |
|---|---|---|
| K1 | key guard removed | KILLED |
| K2 | bool accepted as a key | KILLED |
| K3 | int accepted as a key | KILLED |
| K4 | non-string keys dropped silently (not counted as missing) | KILLED |
| K5 | empty string treated as missing | SURVIVED |
| P1 | payload guard removed | KILLED |
| P2 | payload guard accepts a list | KILLED |
| C1 | missing count inverted | KILLED |
| C2 | distinct set counts None as a key | KILLED (re-run by hand: 11 failed) |
| (-) | one mutant had a mistyped search string and did not apply; replaced by C2 above | not counted |
Totals: 9 mutants applied, 8 killed, 1 survived (8+1 = 9). K5 is a pre-existing, unpinned choice: an event with `token_id: ""` is counted as a distinct token named "" today; whether that should be "missing" is a product call (LOW).

## Not verified
CI/GX10; Linux; the full attestation-reporter suite on this head.
