# C-80: post-merge check on main 75a84c8 (PR 58, C-35) (teammate-don-reviewer, 2026-10-28) - PASS

VERIFIED on the GX10 (fresh clone ~/ff-work/wt-fieldrev-80 at 75a84c8, Python 3.12.3, CI=true, no DB port; each service suite from its own directory; PYTHONPATH = this tree's field-core, field-agent and all service src dirs). main = 75a84c8, 1 commit past c8ecba7, author and committer Don Hagell <13129187+dhagell@users.noreply.github.com>.

## Suites on main (all green)
field-core 884 passed; field-agent 113; agent-registry 232; kill-switch 143; delegation-authority 141; lifecycle-manager 185; spend-governor 101; federation-broker 92; conformance-sentinel 108; compliance-crosswalk 160 (+1 skipped); force-gateway 182; incident-replay 74; attestation-reporter 66; ops-console 171; claude-approver 101; sealed-ledger 648 (+4 skipped); `tools/topology_lint.py`: OK (0 findings, 4 allowlisted); tools/tests (full): 1882 passed, 3 skipped in 8 min 24 s. Nothing red.

## The new rule on main
- operator_auth.py:919 `if r["operator_id"] == BREAKGLASS_ID and not sealed: raise _malformed(...)` present; its three tests exist (test_operator_auth_format2.py:366 `test_rule_the_breakglass_id_must_be_a_sealed_row` [auto, remote], :380 `test_rule_a_revoked_breakglass_id_must_still_be_a_sealed_row`, :389 `test_the_sealed_breakglass_row_is_still_accepted`).
- The five guard mutants still die (field-core format2 + stage0 + operator_rotation_r2, baseline 316 passed): guard removed 3 red; `not sealed` -> `sealed` 56 red; id compare inverted 63 red; guard on every id 63 red; revoked rows exempt 1 red. 5 of 5 killed.

## Does anything else build a non-sealed `don-breakglass` row? No
- Non-test mentions of the id on main: docs/runbooks/v1.2-deploy-rollback.md:1231, 1488, 1490 (prose), operator_auth.py (BREAKGLASS_ID, is_breakglass, the new rule), operator_health.py (one). No json/yaml/csv, fixture, compose file or tool writes the row.
- Tests that build it: test_operator_rotation_r2.py:76, :89 use `rotation: sealed`; keygen format-2 tests use `sealed`.
- R4a migration (#57 rotation.py `migration_candidate`): marks `is_breakglass` ids `sealed`; checked earlier by merging #58 into #57 (260 tests passed). Not re-run on the merged main (#57 is not on main).
- Open, unchanged: the alias-squat LOW from C-76 (an ordinary row may carry the alias `don-breakglass` when no break-glass row exists) is NOT fixed by 75a84c8; finding F-C76-1 stays open.

## Verdict
PASS. NOT verified: the GB10/Fly estates, the runbook text beyond the three grep hits.
