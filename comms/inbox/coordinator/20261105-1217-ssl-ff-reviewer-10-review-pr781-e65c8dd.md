# Review PR #781 (conformance-sentinel: seed manifest expiry follows the clock, S8-23) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `e65c8ddfd4f22475d62ccf27d4e92a602d356b8c` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 4 files: seeded.py (+14/-2), tests/conftest.py (+2/-1), README.md (+1), tests/test_seed_manifest_expiry_s8.py (+55). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- `_seed_expiry(now=None)` = UTC today + 365 days as a date-only ISO string; `_seed_manifest_data(now=None)` uses it; conftest uses the far date 2099-12-31. Leap-year case checked by the test (2040-01-01 + 365 days = 2040-12-31). The shipped `self_manifest.yaml` (2027-06-30) is deliberately untouched and pinned as the operator renewal date, and the README names it: after that date the mint gate refuses every token for that agent (HIGH that this is a real production date, not fixed by this PR, and disclosed by it).
- tests/test_seed_manifest_expiry_s8.py: 6 passed on the head. Sentinel suite (PR: 269) not run by me.
- Other 2027-06-30 time bombs the author lists (field-agent, field-core, delegation-authority, force-gateway, incident-replay, tools tests, demo scripts, manifests): out of this card; I did not check which are in a mint-gate path (not verified).

## Mutants (seeded.py / conftest.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | SEED_EXPIRY_DAYS 30 | RED |
| M2 | literal "2027-06-30" restored | RED |
| M3 | injected `now` ignored | RED |
| M4 | output is a datetime string, not date-only | RED |
| M5 | expiry in the past (-365 days) | RED |
| M6 | `now` dropped inside _seed_manifest_data | RED |
| M7 | conftest text mentions the old literal | RED |
| M8 | conftest expiry changed to 2027-12-31 | RED |
Totals counted from the table: 8 mutants, 8 RED, 0 SURVIVED.

## LOWs (optional, new PR)
1. Two of the six tests are source-text pins (`"2027-06-30" not in seeded.py`/conftest, `"2099-12-31" in conftest`) rather than behaviour; M7/M8 are caught only by that text check. The behavioural coverage of the conftest value is the suite itself running after 2027-06-30 (not simulated by anyone: the author says so; I did not either).
2. The test fixtures using other dates and the production `self_manifest.yaml` renewal need their own card (renewal date 2027-06-30 is the real exposure).
