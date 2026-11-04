# LANE O review: PR 672 (force-gateway S4-24: unknown preset refused with fixed text) @ 72c3555a

Verdict: PASS. UNVERIFIED (cloud, no GX10). Head 72c3555a, 1 commit, 0 behind origin/main, Don Hagell numeric noreply. api.py +3/-5 (two raise sites), tests +44, boundary_echo_allowlist.txt -1 line (the `create_app.preset_text::api-reply` entry removed).

Objections first: (1) the lint allowlist removal is only meaningful if the echo is really gone; it is pinned by the existing tools/tests lint (61 passed at this head) and by the new file, not by anything that exercises the removal itself. (2) The refusal lists the known preset names, which is an information disclosure by design (a made-up marker never appears; the names are config, not secrets); the PR makes that explicit. (3) `inject_force_block` calls `preset_block` and would raise KeyError for an unknown name, but it is reached only after the `PRESETS` check at api.py:953, so no echo path remains; I checked by reading, not by a mutant.

Baseline (unmutated, measured): force-gateway suite 457 passed; tools/tests/test_boundary_echo_lint_c505.py 61 passed. Survivor check ran the whole force-gateway suite and the lint test.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 unknown header: 422, fixed text, lists the known names, never the header | 7 | 7 | 0 | 0 |
| B2 unknown path: 404, fixed text, lists the known names, never the name | 6 | 6 | 0 | 0 |
| B3 a known preset is still served unchanged | 4 | 3 | 0 | 1 |
| Total | 17 | 16 | 0 | 1 |

Totals counted from the table: 17 = 16+0+1; no invalid, no noapply.

Survivor (equivalent): B3 `except Exception` in place of `except KeyError`; `preset_block` raises only KeyError for a missing name, so the behaviour is the same.

Conditions: none blocking. Confidence: HIGH on counts, MEDIUM on completeness of the mutant set (only the two raise sites are in scope). Token/cost: I do not know.
