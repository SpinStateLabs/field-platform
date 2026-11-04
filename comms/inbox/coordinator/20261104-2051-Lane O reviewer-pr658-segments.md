# LANE O review: PR 658 (lifecycle-manager S4-10, ids as one encoded path segment) @ 12310ca7

Verdict: PASS. UNVERIFIED (cloud, no GX10). Head 12310ca7: code+test commit 528aceb8 and a docs anchor refresh 12310ca7; 0 behind origin/main, 2 ahead; both commits Don Hagell numeric noreply. engine.py +12/-8, tests +198, docs/ENVIRONMENT.md 2 lines.

Objections first: (1) the tests build the expected path with their own `seg()` helper, a copy of the source `_seg`; a shared mistake would pass. This is mitigated by literal assertions in `test_the_expected_form_helper_is_what_the_card_asks_for` and `/tokens/%2E%2E/revoke`, and by the kill of every `_seg` mutant below. (2) The wrapping is call-site by call-site (6 sites at engine.py:680, 825, 869, 906, 1080, 1119); a future new id-in-path call is not guarded by any test that scans for plain f-strings. (3) Percent-encoding case is pinned to upper-case `%2E` only for the dot segments; whether a server decodes `%2E%2E` before routing is a deployment property I cannot verify here.

Baseline (unmutated, measured): lifecycle-manager suite 301 passed; `python tools/environment_anchors.py --check` at this head: 0 wrong anchor row(s). I grepped engine.py for id-in-path f-strings: all 6 are wrapped; `/tokens` GET uses `params=` and `/tokens` POST has no id.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 sweep orphan kill path is one segment | 1 | 1 | 0 | 0 |
| B2 provision registry GET/PATCH and governor PUT one segment | 3 | 3 | 0 | 0 |
| B3 decommission kill and token revoke one segment | 3 | 3 | 0 | 0 |
| B4 `_seg` encodes every reserved character | 6 | 6 | 0 | 0 |
| B5 dot segments `.` and `..` spelled %2E | 5 | 5 | 0 | 0 |
| B6 ordinary ids produce byte-identical paths | 4 | 2 | 0 | 2 |
| Total | 22 | 20 | 0 | 2 |

Totals counted from the table: 22 = 20+0+2; no invalid, no noapply. B1 has one mutant because the sweep path is a single call site (below the 4-mutant floor for that behaviour; its 4 sibling call-site mutants sit under B2 and B3, and `_seg` mutants B4 and B5 also reach it).

Survivors (both equivalent, no gap):
- B6 `quote(..., safe="-")`: `-` is already an unreserved character that `quote` never encodes.
- B6 `... + ""`: no-op.

Conditions: none blocking. Optional: a test that greps `engine.py` for an unwrapped `f"/…/{…id…}"`. Confidence: HIGH on counts, MEDIUM on completeness of the mutant set. Token/cost: I do not know.
