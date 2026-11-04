# LANE O review: PR 707 (agent-registry S6-7: PATCH resolves manifest_ref when an operator mode is armed; README, SPEC, comment) @ 97a86272

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 97a86272, 1 commit, Don Hagell numeric noreply (author and committer). Freshness: `git fetch origin main` first; main = ebb027a2; head is 0 behind, 1 ahead; `git merge-tree --write-tree` clean. Change is docs and tests plus one code comment: README row (1 line), SPEC (+3/-1), api.py comment (2 lines), test_d3b_manifest_ref_resolves.py (docstring wording), new test_patch_manifest_ref_by_mode.py (+103). No behaviour change in source.

Objections first: (1) the new file says it "pins the docs so an edit cannot make them drift again"; it checks substrings only, so 7 of my 9 deliberately wrong doc edits pass (below). The code behaviour is pinned well; the docs pin is mostly decoration. (2) The docs claim that log-only means `FIELD_OPERATOR_REGISTRY` is set and enforce means `FIELD_OPERATOR_REQUIRE` is on; I verified that against `field_core.operator_auth.mode()` (packages/field-core/src/field_core/operator_auth.py:280-286: REQUIRE flag gives ENFORCE, else a registry path gives LOG_ONLY, else OFF), so the docs are right; no test pins that mapping. (3) The behaviour sits on the `registry_edit` branch, which also demands operator authentication in enforce mode; the 422 test in enforce mode therefore passes through the credential check first, and the tests do not separate "refused for the ref" from "refused for the credential" except by the 422 status.

Baseline (unmutated, measured): agent-registry suite 319 passed. Survivor check ran the whole suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 armed (log-only, enforce): an unresolvable ref on PATCH is refused 422 and not stored | 7 | 7 | 0 | 0 |
| B2 off: PATCH does not check the ref | 3 | 3 | 0 | 0 |
| B3 a resolvable ref is accepted in every mode | 3 | 3 | 0 | 0 |
| B4 the README row, SPEC and code comment cannot drift from that | 9 | 2 | 0 | 7 |
| Total | 22 | 15 | 0 | 7 |

Totals counted from the table: 22 = 15+0+7; no invalid, no noapply. B4 mutants edit the docs or the comment (not code); each is a wrong statement a reader would believe.

Survivors, 7, all real gaps in the docs pin:
- README row: log-only and enforce env vars swapped.
- README row: the "Declared only (... Enforced in code when an operator mode is armed)" parenthetical removed.
- README row: `registry_edit` changed to `registry_read`.
- SPEC: "log-only or enforce" changed to "enforce only".
- SPEC: "with the operator mode off it is not" changed to "it is too".
- SPEC: "refused 422" changed to "refused 409".
- api.py comment: "armed" changed to "OFF".
Killed by the new file: README "422" to "409", and README "it does NOT check it" to "it checks it".

Conditions: either assert the exact doc sentences the claim relies on (mode mapping, 422, off clause in both README and SPEC) or soften the file's docstring to say it spot-checks the docs. Confidence: HIGH on counts, MEDIUM on classification. Token/cost: I do not know.
