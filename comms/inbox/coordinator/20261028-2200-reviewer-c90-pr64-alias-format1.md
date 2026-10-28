# C-90: PR 64 fix/breakglass-alias-format1 at a8bd47c (C-87, my C-86 LOW) (teammate-don-reviewer, 2026-10-28) - PASS with one rollout LOW

VERIFIED on the GX10 (fresh clone ~/ff-work/wt-fieldrev-64, Python 3.12.3, CI=true, no DB port). 1 commit on main 84d26a4, 0 behind; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com>. Written by the coordinator, reviewed by me.

## The change
operator_auth.py `validate_rows` (shared by format 1 and format 2), +8/-1: inside the alias loop, before the "alias equals an operator id" and "alias shared" rules: `if n == BREAKGLASS_ID and r["operator_id"] != BREAKGLASS_ID: return "alias ... of operator ... is the break-glass identity"`; docstring rule added. Tests: +2 in test_operator_auth_stage0.py (a format-1 file written to disk and loaded with `oa.load_registry`, message starts "operator registry ambiguous: " and contains "is the break-glass identity"; and `validate_rows` next to the real break-glass row).
- My C-86 LOW (format-1 alias squat) is FIXED at a8bd47c (not merged): `validate_rows` now refuses it for both formats.

## Tests
field-core full 950 passed (948 + 2); kill-switch 143, agent-registry 232, delegation-authority 141, lifecycle-manager 185, sealed-ledger 650 (+4 skipped); keygen (3 files) + edge-block + job_grantors tools tests 102 passed. Rule-focused set (stage0 + operator_auth + format2 + operator_rotation_r2) 379 passed.
Mutants (4, all KILLED): rule removed (2 red); `!=` -> `==` on the row id (2 red); `n ==` -> `n !=` (71 red); rule only when no break-glass row is present, i.e. the original squat only (1 red).
No fixture, doc or other test fails: the only repo mentions of the alias are in tests that already use the sealed row.

## What the R4a migration (#57) does with a format-1 file that now fails the rule
Checked by merging #57 (09dcbcd) and #64 in a scratch branch and driving the real rotator with a format-1 file whose seventh row carries `names: ["don-breakglass"]` and no break-glass alias row (probe test, discarded):
- `run_once()` returns `EXIT_FAILED` (1), summary `{'result': 'failed', 'phase': 'publish', 'reason_class': 'validation', 'detail': "operator registry malformed: row 7 ('job-extra'): the alias 'don-breakglass' belongs to the break-glass identity alone"}`. The message comes from `_parse_format2` (PR 63's rule, reached when `migration_candidate`'s output is validated), names the row and the rule, never a key or hash; it is clear.
- The operators file is byte-identical afterwards (`file unchanged: True`); exactly one event is ledgered: `keyrotation.failed {phase: publish, reason_class: validation, reverted: false, generation: null, registry_sha16: null}` under the rotator's id. So the migration is BLOCKED, nothing is written, a human is told: same behaviour as the legacy-row cases in #57's own test `test_a_legacy_row_format2_refuses_blocks_the_migration_not_the_estate`.
- R4a suites on the merged tree (rotation, review fixes, diff_guard, operator_rotate, keygen F4): 152 passed.

## Finding
1. LOW, rollout risk (PROVEN by the same probe): after #64 the SERVICES also refuse that format-1 file. `parse_registry_doc` on it raises `RegistryUnavailable: operator registry ambiguous: alias 'don-breakglass' of operator 'job-extra' is the break-glass identity`. #57's test comment "format 1: still fine ... the estate is never blocked" no longer holds for THIS case: a live format-1 operators file that carries the alias becomes unavailable to every operator-block service on the next restart/reload (LOG-ONLY: `registry_unavailable` is recorded and writes go unattributed; ENFORCE: every guarded write answers 503). That is the intended fail-closed behaviour, but it is a behaviour change for an existing file. Before any deploy of a main containing #63/#64 (the C-8/D-11 catch-up), check each live operators file (GB10, Fly) for `names` containing `don-breakglass` on a non-break-glass row (`grep -c don-breakglass` on the `names` fields, or `operator_keygen --check`): one command per estate. I did not read a live file. Put it in the C-8 plan's pre-deploy checks.
2. INFO: for a FORMAT 2 file the alias is now refused twice (the per-row check in `_parse_format2` from PR 63 first, then `validate_rows`); the two messages differ ("belongs to the break-glass identity alone" vs "is the break-glass identity"). Harmless; keep one if you want a single message.
3. INFO: `operator_keygen --add-to ... --names don-breakglass` is now refused as a side effect (it validates the whole document through `parse_registry` before writing); not run by me.

## Verdict
PASS on the exact head. NOT verified: a live operators file; keygen `--add-to` with the alias.
