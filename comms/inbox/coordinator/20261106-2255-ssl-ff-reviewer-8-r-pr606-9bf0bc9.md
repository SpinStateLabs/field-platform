# Review R-PR606-9bf0bc9: PR 606 (conformance-sentinel: upstream bodies of the wrong shape BLOCK with a named clause; a missing spent_cents no longer counts as zero; scout S-2-22, HIGH CARE)
Head reviewed: 9bf0bc98e6161cedc25362fb242caaa258ea8a03 (2 commits: 9d6b163f the change, 9bf0bc98 the no-echo pins). Behind main; `git merge-tree` against main is clean (tree 70c0ec2f). Policy enforcement point: I read the engine diff and the code around it, not only the tests.

## VERDICT: PASS WITH CONDITIONS (the PR's two fail-opens are closed; the same class remains in two neighbouring checks, reproduced below)

## Checks (HIGH, run by me)
1. Identity: both commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 2 files (engine.py +36/-5, a new test file +228).
2. Code read: `_object_body(resp, what)` is used by the three upstream readers (governor `/status`, `/totals`, delegation `/introspect`): a 200 whose body is not JSON or not an object raises `ConnectionError("<what> answered with ...")` (fixed text, no body), which the engine's existing handlers turn into BLOCK (`D.token` for introspect, `E.spend_cap` for status and totals), so a `null` status body can no longer pose as "no cap"; `_token_ceiling` reads `spent_cents` strictly (bool, non-int and negative are BLOCK `E.spend_cap`, a missing key too, which was the fail-open `int(totals.get("spent_cents", 0))`); a token `scope` that is not a list of strings is BLOCK `D.scope` (a bare string used to make `action not in scope` a substring test).
3. Tests on head: test_upstream_body_shapes 68 passed (a long file: 8 minutes here).
4. Mutants on the engine, 8 run, 8 killed (counted from table; selected with `-k` for speed where noted).
| # | Mutant | Result |
|---|---|---|
| O1 | `_object_body` accepts a non-object | killed |
| O2 | a JSON decode error propagates instead of ConnectionError | killed |
| O3 | a missing `spent_cents` counts as 0 again (the original fail-open) | killed |
| O4 | a bool `spent_cents` accepted | killed |
| O5 | a negative `spent_cents` accepted | killed |
| O6 | a float `spent_cents` accepted | killed |
| O7 | a bare-string token scope accepted | killed |
| O8 | a non-string entry in the token scope accepted | killed |

## Conditions
### C1 (HIGH, confirmed by running): an object `/status` body with a missing, unknown or wrong-typed `state` is treated as "no objection" and the action is ALLOWed
After `_object_body`, step 8 reads `spend.get("state")` and acts only on the exact strings `BLOCK`, `THROTTLED` and `ESCALATE` (engine.py:651-670); anything else falls through to `ALLOW` ("all clauses satisfied"). Probe (test_zz_probe..., a temporary file in my scratch worktree, deleted; reuses the PR's own `govern`/`post` helpers, a valid token with no ceiling and a valid `/totals`): the governor `/status` answering 200 with
- `{}`, `{"state": null}`, `{"state": 5}`, `{"state": ["BLOCK"]}`, `{"state": "block"}`, `{"state": "BLOCK "}`, `{"state": "EXHAUSTED"}`, `{"stat": "BLOCK"}`, and another service's body `{"ok": true, "service": "x"}`
each gives `decision=ALLOW`, no clause; only the exact `"state": "BLOCK"` gives BLOCK (`E.spend_cap`). So a cap that has been reached is invisible to the sentinel whenever the answer is an object without that exact string: schema drift between the two services, a casing change, a caching or routing layer, or a `FIELD_GOVERNOR_URL` pointing at another service that answers 200 with a JSON object. This is the same defect class as the `spent_cents` default the PR fixes, one field over, and the PR's own rule ("a body of the wrong shape is no answer") stops at "is an object".
Fix: require `state` to be one of the governor's values (`OK`, `ESCALATE`, `THROTTLED`, `BLOCK`); anything else is BLOCK `E.spend_cap` with a fixed text; add the nine bodies above to the new test file. The same belongs to the judge-spend gate at engine.py:321 (`spend.get("state") == "BLOCK"`), which also reads `state` unchecked.

### C2 (MEDIUM, confirmed by running): the token's `active` flag is judged by truthiness
engine.py:550 `if not intro.get("active")`. With the delegation `/introspect` answering `"active": "true"` (a string) or `"active": 1` the action is ALLOWed (probe, same method); an empty object, a missing `active` and an empty or missing `scope` are correctly BLOCKed (`D.token`, `D.scope`). A string `"false"` or `"0"` is also truthy in Python, so it passes by the same test (read from the code, not probed). The delegation service sends a JSON boolean, so the exposure is again a different or drifted upstream, but the PR's goal is a strict reading of upstream bodies.
Fix: `intro.get("active") is not True` is BLOCK `D.token`; tests for `"true"`, `"false"`, `1`, `0`.

## Observations (LOW, not conditions)
- The first `_token_ceiling` reasons still carry the token's `max_spend_usd` repr and an exception text (`f"token max_spend_usd {raw!r} is unreadable ({exc})"`, `f"... cannot total spend under this token: {exc}"`); the new texts are fixed, these older ones are not, and an `httpx` error text can hold the URL.
- Introspection `status: "revoked"` with `active: true` is not cross-checked (the delegation service keeps them consistent).

## Not verified
The full sentinel suite beyond the new file; behaviour against a real governor; GX10 16/16.

## Conditions to reach PASS
C1 and C2 in a new commit with tests for each listed body; identity re-check of the new head; re-run of mutants O3 and the new `state` and `active` ones.
