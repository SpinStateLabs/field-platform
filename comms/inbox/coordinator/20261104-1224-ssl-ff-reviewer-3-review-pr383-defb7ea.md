# Review PR 383 @ defb7eaf5c705a820471b1c8904d1f3c4d44d167 (C-804, one startup WARNING when a service starts open) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head defb7eaf as a branch (lineage and conflicts). The logic passes on its own tree. UNVERIFIED (cloud, no GX10).**

## Blocking findings (HIGH, measured)
- F-R383-1 BLOCK: no merge base with current origin/main (97dcfec1; `git merge-base` fails); `git log origin/main..pr383` lists 417 commits (old pre-rewrite history, as PRs 387, 392, 405, 408, 419, 420).
- F-R383-2 BLOCK: the PR's own 2 commits (2b22bac7, defb7eaf above merge base 63e91b21; both Don Hagell noreply, author AND committer) do NOT cherry-pick onto main 97dcfec1. Conflicts: `docs/ENVIRONMENT.md`, `services/agent-registry/src/agent_registry/api.py`, `services/conformance-sentinel/src/conformance_sentinel/api.py` (20 files in the patch; 3 conflict). A rebuild needs hand resolution by the author, so what I measured below is the head on its OWN tree, not a patch that can land.

## Measured on the head's own tree (scratch worktree at defb7eaf)
- Patch: 20 files, +474 -28: new `field_core/startup.py` (`open_settings`, `warn_open`), a call in all 14 services, `operator_auth.py` (+9), docs, 2 test files.
- Baseline unmutated: `packages/field-core/tests/test_startup_c804.py` + `tools/tests/test_startup_open_warning_c804.py` = 78 passed (PYTHONPATH relative, all service `src` dirs on the path).
- Mutants of `startup.py` (both test files run each time; files restored, clean):
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| perimeter secret named only when unset (U1, U2) | 2 | 2 | 0 |
| operator layer named only when asked and only in mode OFF; log-only is not open (U3, U4, U5) | 3 | 3 | 0 |
| `extra` names: shape (fullmatch, UPPER_SNAKE, 64 max, str only) and kept (U6-U11) | 6 | 6 | 0 |
| one warning per service per process (U12, U13, U14) | 3 | 3 | 0 |
| return value, never raises, WARNING level (U15, U16, U17, U18) | 4 | 4 | 0 |
| no value in the line (U19) and separator (U20) | 2 | 1 | 1 (U20) |
Totals counted from the table: 2+3+6+3+4+2 = 20 rows; killed 19; survived 1; anchor failures 0.
- F-R383-3 LOW (U20): the `", "` separator is unpinned (cosmetic).

## Not done
No mutants on the 14 per-service call sites or on `force-gateway`/`sealed-ledger`'s extra names (covered only by the parametrized baseline). The survivor was not run against the whole suite (cosmetic; I do not know what else reads the separator; I did not grep).

## Recommendation (coordinator's call)
Release PR 383. The builder resolves the 3 conflicts on a new branch from current main (a docs conflict in ENVIRONMENT.md: use `python tools/environment_anchors.py --fix` per STATUS MERGE 14), then a fresh independent review.

## Objection
The 19/20 is a statement about the old tree; the conflicts sit in 2 service files that the patch edits, so it must be re-verified after the rebuild.
