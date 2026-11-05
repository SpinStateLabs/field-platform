# Review PR #786 (agent-registry: empty PATCH is a 422, S8-15) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `736ae7ee5494cd200d723f343174df91ca72128e` (draft, base main). Condition 1 is a decision gate, not a code defect.

## Conditions
1. **Don's explicit OK on the behaviour change** (the PR itself says "NEEDS DON'S OK"): `PATCH /agents/{id}` with `{}` or only nulls was 200 plus a `registry.updated {"fields": []}` ledger row (also on a retired agent); it is now 422 with no row. Three existing pinned expectations were edited to match (test_retired_attest_c260.py twice, test_registry_update_validation.py once). I confirm the edits are faithful (below) but a reviewer cannot grant this API change.
2. Do not merge before 1; optional LOWs below go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 4 files: agent_registry/models.py (+7), tests/test_empty_patch_s8.py (+84), test_registry_update_validation.py (2 lines), test_retired_attest_c260.py (6 lines). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Fix: a `model_validator(mode="after")` on `AgentUpdate` raises when every field is None. Only in-repo constructor of `AgentUpdate` outside tests is store.set_status with `status=` (store.py:250), so the internal path is unaffected; the HTTP route is the only place an empty patch arrives. The caller claims (field-core set_status sends status; lifecycle/sentinel send fields) match my grep: PATCH senders in packages/services/tools are field_core clients.py (status) only; I did not trace the lifecycle engine's patch condition line by line (not verified).
- The edited tests: (a) retired agent `{}`: now asserts 422, record unchanged (updated_at included), no ledger event: faithful. (b) `AgentUpdate()` to `AgentUpdate.model_construct()` keeps the store no-op pinned: faithful. (c) `model_construct(name=None, owner=None)` keeps the dump rule: faithful.
- tests/test_empty_patch_s8.py + test_registry_update_validation.py: 22 passed on the head. Registry suite (PR: 316 without the slow race file) not run by me.

## Mutants (models.py validator, one at a time, restored after each; tests: test_empty_patch_s8.py)
| # | Mutant | Result |
|---|--------|--------|
| M1 | validator never fires | RED |
| M2 | `all` to `any` (refuse any None) | RED |
| M3 | falsy instead of None (`""` counts as empty) | SURVIVED |
| M4 | status ignored in the check | RED |
| M5 | domain ignored in the check | RED |
| M6 | manifest_ref ignored in the check | SURVIVED |
| M7 | message text changed | RED |
| M8 | only `name` checked | RED |
Totals counted from the table: 8 mutants, 6 RED, 2 SURVIVED.

## LOWs (optional, new PR)
1. M6: no test patches `manifest_ref` as the only field (a real caller shape: the lifecycle engine patches owner/manifest_ref). Add a sole-`manifest_ref` and sole-`owner` case.
2. M3: no test sends `domain: ""` as the only field, so a falsy-vs-None regression would refuse a valid clearing patch unnoticed.
3. The validator error is a 422 with `loc: ["body"]` and no echo (the PR tests it with a marker); the message text itself is dropped by the registry's handler, so M7 is pinned only by a test of the text on the model.
