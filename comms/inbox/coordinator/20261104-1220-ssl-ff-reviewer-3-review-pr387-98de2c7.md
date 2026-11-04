# Review PR 387 @ 98de2c778176d0d4da7dbbd347ed240895a67923 (C-817 top-level non-string path carriers; stacked compose-check hardening) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head 98de2c77 as a branch (lineage). The patch passes on a clean rebuild; two LOW survivors. UNVERIFIED (cloud, no GX10).**

## Blocking finding (HIGH, measured)
- F-R387-1 BLOCK: no merge base with current origin/main (97dcfec1; `git merge-base` fails); `git log origin/main..pr387` lists 418 commits (old pre-rewrite history, same as PRs 392, 405, 408, 419, 420; many with non-noreply identities, measured in the PR 420 report). It cannot fast-forward.
- The PR's own work is 11 commits above b929f126 (merge base with PR 419's history), all Don Hagell noreply for author AND committer (measured). The first of them (76792597, "apply the compose bind-source allowlist to the RESOLVED model") is ALREADY on main: its cherry-pick is empty.

## The patch, measured on a clean rebuild (main 97dcfec1 + the other 10 commits, `git cherry-pick b929f126..pr387` with the empty one skipped; no conflict)
- 10 files, +1295 -48: `tools/compose_bind_rules.py` (shared name rule, `CALLER_KEYS_ROOT`, key allowlists), `tools/compose_resolved_check.py` (+191), runbook (+1), and 6 test files incl. `test_compose_static_nonstring_c817.py` (the card's own, 66 lines). Scope is wider than the PR title: it carries C-715, C-823, C-932, C-1049 work too.
- Baseline unmutated: the 7 test files that reference the two tools (these are the only files in the tree that do; grep) = 1061 passed (76 s; relative `PYTHONPATH=packages/field-core/src:tools`). No baseline failure.

## Mutants (the 7 files, `-x`; each survivor ran the whole 7-file set to completion; files restored, worktree clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| C-817 static pins: volume device and secret/config file non-string are violations, unknown shape a violation never a crash (V1-V10) | 10 | 10 | 0 |
| C-817 resolved check: device and file must be text, message kept, not read as clean (R1-R6) | 6 | 6 | 0 |
| device None guard and tmpfs exemption (R7-R10) | 4 | 2 (R8, R9) | 2 (R7, R10) |
| exit-3 shapes: empty services, non-dict model, non-mapping service, non-list volumes (R11-R14) | 4 | 4 | 0 |
| shared name rule: .git anywhere, .env and .env.*, case-insensitive (N1-N6) | 6 | 6 | 0 |
Totals counted from the table: 10+6+4+4+6 = 30 rows; killed 10+6+2+4+6 = 28; survived 2; anchor failures 0.

## Survivors
- F-R387-2 LOW-MEDIUM (R7): remove the `device is not None` guard in `check_model`; a volume with `driver_opts` and NO `device` would then be reported "None is not a string" (a false violation). No test has a volume with driver_opts and no device.
- F-R387-3 LOW (R10): `device: tmpfs` with no `type: tmpfs` is exempt only because of the `or`; the type-only form is pinned (R9 killed), the device-only form is not.
Optional pins, NEW PR only.

## Not done
No mutants for the C-932 (copied-alone, exit 3 without PyYAML, stale sibling) and the `--realpath` behaviours (commits a24baa55, 00352965, e57632fe); those are covered only by the baseline pass. I did not run the whole `tools/tests` directory (collection needs service packages absent from my venv), only the 7 files that reference these tools. Honest gap: this review is complete for C-817 and the shared rules, partial for the rest of the stack.

## Recommendation (coordinator's call)
Release PR 387; rebuild on current main (10 commits, clean today; skip 76792597, already landed) as a new draft PR, then a fresh independent review. Splitting the C-932/C-1049 commits out would make the review smaller.

## Objection
Approving the old head would approve an unmergeable branch; this verdict covers the rebuilt patch only.
