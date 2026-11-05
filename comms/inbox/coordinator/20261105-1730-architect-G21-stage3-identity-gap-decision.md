# DECISION G21: Stage 3 identity gap (rows C1/T6). Architect (ssl-fp-architect), 2026-11-05. Decided under Don's delegation (everything except money and features).

## Decision
1. NO job row gains `registry_edit` and NO row gains `bypass_operator_list`. The gap is closed by (a) the shipped P29 behaviour (PR 46: an unchanged re-provision sends no PATCH, so renewal needs no `registry_edit`) and (b) one roster rule and one manifest rule for the remaining case, a real change of `owner`, `manifest_ref` or `domain`:
   - A change of owner/manifest_ref/domain is a HUMAN edit by `don-admin` (the only v0.4 row with `registry_edit`), never a job-identity act.
   - Every manifest whose `kill_switch.authorized_operators` is non-empty adds the id `don-admin` to that list, so `check_record_authorized` passes for `don-admin`. The list matches operator id OR alias (`operator_auth.py` `check_authorized`: refuses only when the id is not listed and no alias is listed). No alias is shared, so `validate_rows` (alias unique to one row) is untouched.
   - `job-provision-gb10` stays `register, caps, mint, revoke` PLUS `mint_for_others` if the shipped row lacks it (verify in the test fixture: C1 mints with a display-name grantor, which needs `mint_for_others`; see `check_granted_by`). No `registry_edit`, no alias, no list exemption.
2. Under REQUIRE a job identity that attempts the changing PATCH gets 403; the engine reports it and does not retry. `lifecycle provision` surfaces `registry_outcome: "edit_refused"` (non-zero exit) with text naming `don-admin` as the actor. OFF and LOG-ONLY behaviour stays byte-identical.
3. Runbook: replace the OPEN ITEM (v1.2-deploy-rollback.md:1716-1730) with this rule and the `don-admin` procedure; the T6 row says "`don` for unchanged re-runs; a changed manifest_ref is `don-admin`".

## Rationale (HIGH unless tagged)
- `registry_edit` guards the list itself: agent_registry api.py:241-256 says replacing `manifest_ref` or `owner` "could defeat that list". Giving it to a job row lets that row repoint an agent at a manifest with an empty `authorized_operators` (an empty list means no restriction beyond authentication). That weakens REQUIRE; rejected.
- Renewal does not need it: `test_provision_unchanged_p29.py` states the unchanged re-run sends no PATCH. Mint uses `mint_for_others`, which is not list-bound for a non-verifier. The real gap is smaller than rows C1/T6 read.
- An alias cannot be shared (`validate_rows`), and the list accepts the row's id, so no second alias is needed.
- Cost: manifest-list additions plus one engine message; no `operator_auth` code change. MEDIUM on which in-repo manifests are alias-listed (builder greps `authorized_operators`; not enumerated here).

## Alternatives rejected
- A: `registry_edit` on `job-provision-gb10`. Weakens the list (above).
- B: `bypass_operator_list` on a job row. Defeats every list; C-1003/C-805 go the other way.
- C: share Don's alias with `don-admin`. `validate_rows` refuses the whole file (503 under REQUIRE).
- D: `registry_edit` on `don`. Merges the human kill row with the edit-the-list scope (LOW: design v0.4 is not in this repo).
- E: engine stops PATCHing altogether. Removes a legitimate edit path and changes flags-off output.

## Risk
- A manifest listing only the alias and not `don-admin` still blocks `don-admin` (403). Test: grep every shipped manifest with a non-empty list.
- Listing `don-admin` widens kill/revive reach only if `don-admin` holds those scopes; v0.4 says it does not (Q3 (c)). Test asserts it. MEDIUM (design outside repo).
- `mint_for_others` may already be on the row: do not add twice. This card changes repo docs, demo rows and manifests only; installing the real operators file is G17 (Don's).

## Exact done-when test
New file `services/lifecycle-manager/tests/test_provision_alias_listed_require_g21.py`, real registry, ledger, delegation, governor, kill-switch TestClient apps as in `test_provision_unchanged_p29.py`; REQUIRE set only inside the tests.
Fixture: operators file with `job-provision-gb10` (register, caps, mint, mint_for_others, revoke; no alias, no registry_edit), `don-admin` (registry_edit), `don` (alias `Don Hagell, Spin State Labs`); manifest `authorized_operators: ["Don Hagell, Spin State Labs", "don-admin"]`.
1. Alias-listed agent renewed under REQUIRE: provision twice as `job-provision-gb10`; second run exit 0, `registry_outcome == "unchanged"`, zero PATCH recorded, a new token minted. Mutant: engine always PATCHes -> fails with 403.
2. Same identity, changed `manifest_ref`: 403, stored record unchanged, outcome `edit_refused`, non-zero exit. Mutant: grant `registry_edit` to the job row -> test 2 fails.
3. `don-admin` PATCH with the changed `manifest_ref`: 200, ledger row carries `don-admin` as the authenticated id; a manifest listing only the alias: 403 for `don-admin`.
4. `don-admin` scopes contain neither `kill` nor `revive`; no shipped row holds `bypass_operator_list` except service rows.
5. OFF and LOG-ONLY CLI result JSON byte-identical to main (golden).
Gate: CI green and GX10 run on the exact head; draft PR; flags off.
