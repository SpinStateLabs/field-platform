# LANE O review: PR 659 (lifecycle-manager S4-11: _persist temp name, /findings shape, operator) @ 89d78b77

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 89d78b77: code+test commit f6afaf52 and a docs anchor refresh 89d78b77; 0 behind origin/main, 2 ahead; both commits Don Hagell numeric noreply. api.py +30/-9, tests +206, docs/ENVIRONMENT.md 2 lines.

Objections first: (1) the stripped-operator test uses "  Don Hagell  ", which is already title case; a validator that returns `v.title()` passes (measured), so "stored exactly as sent apart from strip" is unpinned. (2) The persisted file format `indent=2` is not pinned; the code comment and docstring talk only about names and mode. (3) The `except BaseException` cleanup is pinned only through an `OSError` from `os.replace`; a narrower `except OSError` is indistinguishable by any test here (the realistic non-OSError path, json.dumps failing, happens before the temp file exists, so I count it equivalent).

Baseline (unmutated, measured): lifecycle-manager suite 302 passed; `python tools/environment_anchors.py --check` at this head: 0 wrong anchor row(s).

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived | Invalid |
|---|---|---|---|---|---|
| B1 temp name unique per write | 5 | 3 | 0 | 2 | 0 |
| B2 a failed write removes its temp and re-raises | 4 | 3 | 0 | 1 | 0 |
| B3 persisted file keeps the umask-default mode and format | 4 | 3 | 0 | 1 | 0 |
| B4 non-object or unreadable state file is a fixed 500 without the path | 7 | 6 | 0 | 0 | 1 |
| B5 blank operator is a 422 | 4 | 4 | 0 | 0 | 0 |
| B6 operator max 200, stored stripped and otherwise unchanged | 6 | 5 | 0 | 1 | 0 |
| Total | 30 | 24 | 0 | 5 | 1 |

Totals counted from the table: 30 = 24+0+5+1. The 1 invalid (B4, an f-string using `exc` after I had removed it from the `except`) is excluded and not a kill.

Survivors, 5 = 2 real gaps + 3 equivalent:
Real gaps:
- B3 `json.dumps(payload)` without `indent=2`: file format unpinned.
- B6 `return v.title()` in the operator validator: no test value distinguishes it.
Equivalent:
- B1 temp name `<name>.<token_hex>.tmp` (no pid or thread): the 32-bit random part alone keeps names distinct in the tests; pid and thread are belt and braces.
- B1 temp name `<name>.<thread>.<token_hex>` (no pid): same.
- B2 `except OSError:` instead of `BaseException`: no reachable non-OSError after the temp exists in these tests (see objection 3).

Conditions: add a mixed-case operator to the strip test; add an assertion on the `indent=2` format or drop the claim. Confidence: HIGH on counts, MEDIUM on gap/equivalence classes. Token/cost: I do not know.
