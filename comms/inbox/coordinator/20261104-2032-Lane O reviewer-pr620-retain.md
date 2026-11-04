# LANE O review: PR 620 (force-gateway resolve_retain tests) @ 9102e6b8

Verdict: PASS. UNVERIFIED (cloud, no GX10). Head 9102e6b8 = test commit 63810214 + a merge of main; tests only (1 file, +98), both commits Don Hagell numeric noreply.

Objections first: (1) the pins record current behaviour, including `int()` quirks (underscores, Arabic-Indic digits, "+4"); if the parse is hardened these tests must change. (2) The prune test only checks one route with keep_at_least=0. (3) docs/ENVIRONMENT.md says "non-integer or blank falls back"; the test file correctly notes "١٢" is an integer, which the doc wording does not.

Baseline (unmutated): new file 39 passed; force-gateway suite 487 passed.

| Behaviour | Mutants | Killed (file) | Killed (older tests only) | Survived | Invalid |
|---|---|---|---|---|---|
| B1 integer used as read | 5 | 3 | 0 | 2 | 0 |
| B2 zero/negative clamp to 1 | 4 | 4 | 0 | 0 | 0 |
| B3 junk/blank/unset falls back to default | 6 | 4 | 0 | 2 | 0 |
| B4 store retain: env / explicit / explicit zero | 5 | 4 | 1 | 0 | 0 |
| B5 prune to resolved retain | 4 | 3 | 1 | 0 | 0 |
| Total | 24 | 18 | 2 | 4 | 0 |

Totals counted from the table: 24 = 18+2+4+0.

Survivors (all 4 equivalent, no pin gap):
- B1 `.strip()` before `int()`: int() already strips whitespace.
- B1 `int(..., 10)`: same result for every decimal string.
- B3 `except (ValueError, OverflowError)`: int(str) cannot raise OverflowError.
- B3 `except Exception`: int(str) raises only ValueError here.

Condition (minor): the prune pin does not exercise keep_at_least > 0 (the per-route window); covered elsewhere only by older tests (B5 mutant 4 killed by older tests only). Confidence: HIGH on counts, MEDIUM on equivalence. Token/cost: I do not know.
