# Review PR 623 (S3-3: DOA roster refuses duplicate grantors and a non-finite max_spend_usd) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `a6e0be5dedcb1ace7cbe1bd5828feba0a87f9597` (no conditions beyond the standard CI and GX10 on the landed head).

## Checks (HIGH, run by me)
- Identity: 3 commits (two work commits and a merge of main), author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 3; trailers Sonnet 5.5 (merge: none); .github/: 0 files. 2 files: delegation_authority/doa.py (+13/-2), tests/test_doa_roster_duplicates_and_finite.py (+82). Based on b963407a; main is 250154d3; a trial merge into current main is clean.
- Code read: a `model_validator(mode="after")` on `DoaRoster` refuses a second row for the same grantor by exact string (active or inactive; case or whitespace differences are NOT duplicates, since `find()` is exact), surfacing through the loader as `DoaRosterError`, so the mint gate answers 503 "refusing to mint" (fail closed); `max_spend_usd` gets `allow_inf_nan=False` (with `ge=0`, which already refused `-.inf` and `.nan`).
- Blast radius: I loaded every roster in the repository (`manifests/doa-roster.example.yaml`, 3 grantors, and the upgrade-smoke fixture, 1 grantor): no duplicate grantors, so no shipped roster becomes unloadable. `tools/tests/test_generate_doa_roster.py` 29 passed (the generator output still loads).
- Tests on the exact head (Windows): the new file 13 passed (the PR said 6; the second commit added two-row, inactive and whitespace cases). The whole delegation-authority suite was green (257) when I ran it for PR 828 on the same code area; I did not repeat the 12-minute run for this small change.
- A mint-gate note (pre-existing, not changed here): the 503 detail is `DOA roster unavailable — refusing to mint: <exc>` and `<exc>` includes the roster file path, plus pydantic's text. For the new duplicate error, pydantic truncates `input_value`, so only the grantor name and the path appear (I checked: no scope or spend value in the message).

## Mutants (11 on doa.py vs the 13 tests; counted from the table)
| # | mutant | result |
|---|---|---|
| D1 | duplicate check removed | KILLED |
| D2 | compared case-folded (over-strict) | KILLED |
| D3 | compared stripped (over-strict) | KILLED |
| D4 | only adjacent duplicates refused | KILLED |
| D5 | inactive duplicates exempt | KILLED |
| D6 | first row skipped | KILLED |
| D7 | validator runs before the model is built | KILLED |
| D8 | error text also echoes all rows | SURVIVED |
| F1 | `allow_inf_nan` removed | KILLED |
| F2 | `ge=0` removed | KILLED |
| F3 | `allow_inf_nan=True` | KILLED |
Totals: 11 mutants, 10 killed, 1 survived (10+1 = 11). D8 is a LOW gap: nothing asserts that the duplicate message names only the grantor; with the PR's own message pydantic truncates the input, so no leak today.

## Not verified
CI/GX10; Linux; the whole delegation-authority suite on this head.
