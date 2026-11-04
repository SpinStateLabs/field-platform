# LANE O review: PR 675 (sealed-ledger tests for parse_instant, parse_bound, require_https) @ 5f0db836

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 5f0db836, 1 commit, tests only (1 new file, +72), 0 behind origin/main, Don Hagell numeric noreply. No source change.

Objections first: (1) several pins restate Python stdlib behaviour (`datetime.fromisoformat` accepting `Z` and a bare date, `urlsplit` lower-casing the scheme so `HTTP://` is refused); they hold on this interpreter (3.13) and `requires-python` is `>=3.11` in services/sealed-ledger/pyproject.toml, but I ran only 3.13. (2) The naive-is-UTC pin passes under any host timezone only if the code does `replace`, not `astimezone`; my environment is UTC, so that one distinction is invisible to this run. (3) `parse_bound` echoes the caller's value (`{value!r}`) in `InvalidTimeBound`; that is existing behaviour and out of this PR's claim, but the new test pins only the prefix, so it neither pins nor forbids the echo.

Baseline (unmutated, measured): the three older sealed-ledger files that touch these functions (test_time_filters, test_witness, test_caller_signing_f2b) 113 passed; full sealed-ledger suite 828 passed, 5 skipped (138 s). Survivor check ran those three files, not the full suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived | Invalid |
|---|---|---|---|---|---|
| B1 naive timestamp taken as UTC | 4 | 2 | 0 | 1 | 1 |
| B2 an offset is kept, not normalised to UTC | 4 | 4 | 0 | 0 | 0 |
| B3 garbage is ValueError, a non-string is TypeError | 4 | 4 | 0 | 0 | 0 |
| B4 parse_bound: None is open, errors wrapped with the name | 6 | 4 | 0 | 2 | 0 |
| B5 require_https: https with a host, trailing slashes stripped | 10 | 8 | 0 | 2 | 0 |
| Total | 28 | 22 | 0 | 5 | 1 |

Totals counted from the table: 28 = 22+0+5+1. The 1 invalid (B1, `timedelta` not imported in filters.py, a NameError) is excluded and not a kill.

Survivors, 5 = 4 real gaps + 1 equivalent:
Real gaps:
- B1 `parsed.astimezone(timezone.utc)` for naive input: treats naive as host-local time; identical here only because this host is UTC. A non-UTC host would differ. Not testable without setting TZ in the test.
- B4 `except ValueError` only: a non-string bound (TypeError) would escape `parse_bound` instead of becoming `InvalidTimeBound`; the TypeError path of `parse_bound` is unpinned.
- B4 message without the `{value!r}` suffix: only the prefix is asserted.
- B5 `url.rstrip("/").lower()`: case of the returned URL is not pinned (all test URLs are lower case).
Equivalent:
- B5 `url.strip("/")`: differs from `rstrip` only for a leading slash, which `require_https` already refuses.

Conditions: add a non-string `parse_bound` case; assert the full message or state that the echo is intended; add a mixed-case URL path to the https test; set TZ in one naive-timestamp test. Confidence: HIGH on counts, MEDIUM on gap classification. Token/cost: I do not know.
