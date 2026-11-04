# LANE O review: PR 689 (conformance-sentinel S5-13: bound /check fields, shape-check agent_id before the registry) @ 7c927109

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 7c927109, 1 commit, 0 behind origin/main, merge clean, Don Hagell numeric noreply. engine.py +38/-4 net of the diff stat (42 changes), tests +125.

Objections first: (1) the new "R.unregistered without a registry call" reason still interpolates the caller's id (`agent '<id>' is not in the registry`), now into a 200 body and the ledger payload; it is capped at 200 characters, but it is an echo, and the test asserts only the phrase "not in the registry" so removing the id passes. (2) The test `test_deeply_nested_context_is_a_422_not_a_500` accepts 200 or 422, and at depth 5000 on this interpreter (3.13) `json.dumps` succeeds, so the RecursionError branch is never reached; the claim in the test name is unpinned. (3) The id pattern is a copy of agent_registry.models (`^[a-z0-9][a-z0-9._-]*$`, models.py:22 and :52), not an import; the two can drift, and no test links them.

Baseline (unmutated, measured): conformance-sentinel suite 288 passed. Survivor check ran the whole suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 limits are 200, 200, 2000, 50 keys, 16 KiB | 5 | 5 | 0 | 0 |
| B2 each of agent_id, token_id, action is capped | 5 | 5 | 0 | 0 |
| B3 context: key count, byte size, plain JSON | 11 | 6 | 0 | 5 |
| B4 shape-check before the registry call | 9 | 8 | 0 | 1 |
| B5 the block is the ordinary R.unregistered BLOCK naming the id | 4 | 3 | 0 | 1 |
| Total | 34 | 27 | 0 | 7 |

Totals counted from the table: 34 = 27+0+7; no invalid, no noapply (the first B5 attempt had 4 mutants whose anchor text did not match the file; I fixed the anchors and reran them, and those 4 are what the table counts).

Survivors, 7 = 6 real gaps + 1 equivalent:
Real gaps:
- B3 `if size >= CONTEXT_MAX_BYTES`: the exact 16384-byte boundary is unpinned (tests use MAX-20 and MAX+large).
- B3 `except (TypeError, ValueError)` without RecursionError: the RecursionError branch is never reached (see objection 2).
- B3 `size = 0` in that branch: a non-JSON or too-deep context would be accepted; the branch is unexercised.
- B3 `... not plain JSON: {exc}`: echoes exception text; the branch is unexercised.
- B4 id pattern without `_`: underscore ids are allowed by the registry pattern; no test pins `_`.
- B5 reason without the id: only the phrase is asserted.
Equivalent:
- B3 `except (TypeError, RecursionError)` without ValueError: `json.dumps` of a context that arrived as a JSON request body cannot raise ValueError here (MEDIUM; no circular or non-JSON values can come from the wire).

Conditions: add the exact-16384-byte case (accepted) and 16385 (refused); force the RecursionError branch (monkeypatch `json.dumps` or set a lower recursion limit); add an underscore id; decide whether the reason should echo the id and pin it either way. Confidence: HIGH on counts, MEDIUM on gap classification. Token/cost: I do not know.
