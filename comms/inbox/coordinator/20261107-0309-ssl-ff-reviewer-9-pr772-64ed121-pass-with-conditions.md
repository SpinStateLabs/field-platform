VERDICT: PASS WITH CONDITIONS on 64ed12150259bd27ce75c6e9aeedcf7e8670678e  (ssl-ff-reviewer-9; Windows, Python 3.14.2, no GX10, CI not read). Re-review after the builder merged main (which had landed PR 508's named refusals for a malformed n8n export) into reviewer-10's PASSed branch. The merge keeps main's structure and adds only the string-type check and the 1 MiB cap. One required fix: the new size check introduces a 500 for a deeply nested export that main answers with 200.

R-PR772-64ed121, PR 772 (agent-registry: scan_n8n_export wrong shapes and a size cap; S8-14). Applies to this head only. The fetched pull/772/head is 64ed1215: the original commit (8f9b8aa6) and a merge of main (ccd013d4). The base is current main (0 behind); `git merge-tree` is clean. Against main the PR is discover.py +11/-2, api.py +6/-1 (a field description), docs/ENVIRONMENT.md +1/-1 and a new test file +96. Nothing under .github/.

OBJECTIONS FIRST
1. REGRESSION, measured: the new `check_size(json.dumps(export, default=str), "n8n_export")` raises RecursionError for a deeply nested export, which the API does not catch: a POST /discover whose `n8n_export.name` is a list nested 16,000 deep answers 200 on current main and 500 Internal Server Error on this head (same body, same box; depths 5,000, 8,000 and 12,000 give 200 on both). I confirmed the cause directly: `json.dumps` on that value raises RecursionError at depth 16,000 here. 20,000 and 100,000 deep are rejected earlier with 400 "error parsing the body" on both. So an input class that worked now crashes, in a scanner whose purpose is to answer with a verdict or a named refusal, and the PR's claim is exactly that a wrong shape is a 422 never a 500. This is the same Python 3.14 window as the deep-pack gap in PR 788 and the loader gap in PR 508 (a body that the JSON reader accepts but a later recursive call cannot walk). MEDIUM, HIGH confidence on the behaviour and the cause; I measured on 3.14.2 only (CI's matrix includes 3.11 to 3.14, where the window may sit at a different depth).
2. Mutant Z7 (a node `type` of null, 0, false, [] or {} treated as "" through `node.get("type") or ""`) SURVIVES the PR's 17 tests. Today's code refuses them all (probe: type null and type ["x"] both answer 422 "type is not a string"), but the test lists number and object types that are truthy, not the falsy ones, and reviewer-10 already noted the null case as unpinned. A later refactor to `or ""` would let a falsy non-string type scan as no AI node, which is the false assurance this PR exists to prevent. LOW-MEDIUM. HIGH.
3. The size cap is on the serialized export (1 MiB), the response is not bounded by it: a workflow named by about 1,040,000 characters (just under the cap) answers 200 with a 2,080,559-byte body, since the name is returned twice (`identifier` and `display_name`). 5,000,000 characters answers 422 `n8n_export is 5000080 bytes; the scanner accepts at most 1048576 (1 MiB)` (sizes only, no value); a 200,000-character non-ASCII name is 422 because `json.dumps` escapes it to about 1.2 MB. So the cap counts escaped serialized bytes, not characters: 200,000 non-ASCII characters (1,200,080 bytes) is refused while 1,040,000 ASCII characters is accepted. LOW. HIGH (measured).
4. Behaviour change: a node with `"type": null` used to scan as "" and is now a 422 (reviewer-10 noted it); measured 422, fixed text "n8n export: workflow 0 node 0 type is not a string", position zero-based as main's refusals. HIGH.
5. 200,000 tiny nodes (3,000,024 serialized bytes) now answer 422 at the cap; before the cap they were scanned. By design. HIGH.

ASSUMPTIONS
A1 The probes ran in-process through the real app with a tmp store; the 16,000-deep body was sent as raw JSON text (the client's own encoder cannot build it). A2 Mutant Z5 below (coercing with str() after the type check) is equivalent, because the check above it already refuses a non-string.

REASONING / CHECKS
1. Diff read against main (discover.py): `scan_n8n_export` now refuses a node whose type is not a string (named, zero-based position, no value) and runs `check_size` on the serialized export first; the docstring and the `n8n_export` field description state both rules. A missing `nodes` key is still an empty workflow. HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> (the second is the merge); trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): tests/test_n8n_scan_shapes_s8.py 17 passed, 0 failed (15 s). I did not run the whole agent-registry suite (about 22 minutes here); the builder reports main's n8n and shape tests passing together with this file (51 passed). HIGH on what ran.
4. Mutants on a copy of the head, discover.py, the new test file only (-x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| Z1 | the size check removed | KILLED |
| Z2 | the size check labelled for another input | KILLED |
| Z3 | the size check removed from the scan | KILLED |
| Z4 | the string-type check removed | KILLED |
| Z5 | the type coerced with str() after the check | SURVIVED (equivalent, assumption A2) |
| Z6 | the type check only for lists | KILLED |
| Z7 | a falsy non-string type accepted as "" | SURVIVED (objection 2) |
| Z8 | the type refusal echoes the type | KILLED |
| Z9 | the workflow position reported one-based | KILLED |
| Z10 | a non-list `nodes` skipped | KILLED |

Counted from the table: 10 run, 8 KILLED, 2 SURVIVED (Z5 equivalent; Z7 a real gap), 0 NOT APPLIED. Reviewer-10's eight (M1 to M8) are covered by Z1 to Z10 on the merged code. HIGH.

CONDITIONS
C1 (required; a condition fix on the head) catch RecursionError (and ValueError or TypeError) around the `json.dumps` in the size check and answer with a named refusal ("n8n_export is nested too deeply") through ScanInputError, with a test at a depth that main accepts and the head crashes (16,000 deep on 3.14.2, or lower the limit explicitly by counting depth). Re-measure against main with the same raw bodies.
C2 (non-blocking) pin the falsy non-string types (null, 0, false, [], {}) so Z7 dies.
C3 (non-blocking) say that the cap counts escaped bytes, and consider bounding what the response echoes (the workflow name twice).
C4 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
The whole agent-registry suite on this head, GX10 / Linux, CI, the recursion window on Python 3.11 to 3.13.

CONCLUSION
The merge is sound: main's refusals are kept, the string-type check and the 1 MiB cap are the only additions, 17 tests pass, 8 of 10 mutants die (one equivalent, one falsy-type gap), identity correct. But the cap's serialisation turns a 16,000-deep export from a 200 into a 500, which is the failure the PR was written to remove. PASS WITH CONDITIONS: C1 required, C2 and C3 optional, C4 the gate.
