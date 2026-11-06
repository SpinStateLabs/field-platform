# Review PR #835 (G17 repo side: ten-row operators file template + tests) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `4d7f4658828a3e0ee717696c71ab4fa816a2cf06`.

## Facts (HIGH, read from the head)
- 1 commit (4d7f4658); 3 files: docs/templates/operators.g17-template.json (new, 10 rows), tools/tests/test_operators_template_g17.py (new), docs/runbooks/v1.2-deploy-rollback.md (+2 lines). No production code; nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Tests: 16 passed on the head (1.2 s). `operator_keygen.check_file` accepts the template ("rows: 10 (active 10, revoked 0)"), refuses a service row holding `assert_operator`, and refuses a verifier-scoped row (kill, revive, revoke, mint, mint_for_others) without the `svc-verifier-` prefix.
- Public-repo check: hashes are `0...01` to `0...0a` placeholders; no address, URL, `fok_` key, or estate value (the test pins the last three).

## Scopes checked against the sources in the repo (the design v0.4 is not in the repo: not in source for the human rows)
- svc-killswitch (`kill, revive, drill, bypass_operator_list, ledger_attribute`, prefix `kill.`), svc-lifecycle (`kill, ledger_attribute`, `lifecycle.`, `orphan.`), svc-registry and svc-delegation (`ledger_attribute`, own prefix): match the v0.4 column of the runbook (section 7 rows S1, S2, S4/S5).
- job-renewal-gb10 / job-renewal-rog = `mint, revoke` (runbook row T3; token-renewal.md l.220: no `mint_for_others`). Match.
- job-provision-gb10 = `register, caps, mint, mint_for_others, revoke`: the runbook C1 row still says `register, caps, mint, revoke`, but the architect's G21 decision (comms/inbox/coordinator/20261105-1730-..., point 7 and fixture) says the row is those four PLUS `mint_for_others` because C1 mints with a display-name grantor (`check_granted_by`, operator_auth.py:1520-1534). The template follows the decision. No `registry_edit`, no `bypass_operator_list` on any job row, as G21 requires. Match.
- don (no `registry_edit`) and don-admin (holds `registry_edit`, no kill or revive) match G21 and runbook T6/OPEN ITEM text; don-breakglass `kill, revive, bypass_operator_list` matches runbook l.1569 (not verifiable beyond that).

## Mutants (mine, 22 hand mutants on the template JSON, one at a time, file restored from backup; tree clean afterwards). Counted from the output:
- RED 15: assert_operator on a service row; id renamed; row dropped; duplicate placeholder hash; real-looking hash; registry_edit on a job row; bypass on a job row; registry_edit on don; registry_edit dropped from don-admin; svc-registry and svc-delegation prefixes changed; revoked status; URL in `names`; row order swapped; verifier-scoped row without prefix.
- SURVIVED 7 (scope pins missing): kill+revive added to don-admin (G21 invariant); `mint_for_others` added to job-renewal-gb10; `mint_for_others` dropped from job-provision-gb10; `bypass_operator_list` added to svc-registry; dropped from svc-killswitch; `orphan.` dropped from svc-lifecycle prefixes; `bypass_operator_list` dropped from don-breakglass.
- The test pins ids, hashes, `assert_operator`, no registry_edit/bypass on jobs, registry_edit only on don-admin, and two prefix lists; the other scopes are not pinned, so the runbook sentence "shape and scopes checked by ..." overstates: shape yes, scopes partly.

## Test design note (LOW)
- `test_a_file_missing_any_one_of_the_ten_ids_is_refused` checks the test's own `missing_ids` helper against a file the test built: it cannot fail on the template or any production code (keygen `--check` validates rows, not the roster, as the docstring says). The card's "refuses missing ids" is met only by that local helper; the real pin is the first test (template holds exactly the ten ids in order).

## Conditions
None.

## Optional LOWs (new PR only; head is frozen after this PASS)
1. Pin the remaining scopes per row (the 7 survivors), at least the G21 invariants: don-admin holds neither kill nor revive; only service rows and don-breakglass hold `bypass_operator_list`; only job-provision-gb10 holds `mint_for_others` among job rows.
2. Reword the runbook line to say what is pinned, or add the pins.
3. Update the runbook C1 row (`register, caps, mint, revoke`) to say `mint_for_others` per G21, or the template and runbook disagree on the face of it.

## Not covered
Did not install or run anything against an estate; did not check design v0.4 (not in repo); did not rebase on current main (PR 817 / G21 may touch the same runbook region).
