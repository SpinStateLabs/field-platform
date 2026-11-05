# Review PR 798 (rebuild of 400, C-1032 compose stack re-cut) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `ba1d32b618a0682a2f80f4894672cdbe58eaa30d` (no conditions).

## Rebuild fidelity (HIGH, run by me)
- 14 commits, all author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- `git patch-id --stable` compared pairwise, original (pr400 head a4294baa, base acaf5f24) vs rebuild: 14 of 14 identical. Net diff patch-id of rebuild vs main (897fa1e62884) == net diff of the original; 11 files, +1558/-50 both.
- The 4 re-authored commits (originals authored by bare dhagell@users.noreply) differ only in author metadata; patches same. Original first 10 already carried the right email.
- Merge-base of head with current main is aab217d3 (main is now 869cf2ed; PR is not rebased on it, merge-1/GX10 must rebase).

## Tests on exact head (Windows, PYTHONPATH relative)
tools/tests/test_compose_*.py + test_environment_doc + test_environment_anchors_c1116: 1187 passed, 8 skipped, 2 failed. The same 2 (`test_a_symlinked_source_is_followed_only_with_realpath`, `test_docker_runs_only_with_run_compose_and_only_for_config`) fail on unmodified origin/main (87 passed, 2 failed in that file): POSIX assumptions, pre-existing, not Linux-verified by me.

## Code read
No defect found in compose_resolved_check.py / compose_bind_rules.py. Exit-3 contract coherent (usage, read errors, unknown shapes, sibling import failure prints class name only). Runbook addition states the check is optional and unwired. Limits are stated in the docstring, not hidden.

## Mutants (18, targeting the last four commits' behaviours, run on compose test files; counted from table)
| group | mutants | killed |
|---|---|---|
| tmpfs NAME-only exemption / bind option (T1-T6) | 6 | 6 |
| BOM / empty text (B1-B4) | 4 | 4 |
| sibling import -> exit 3, class name only (I1-I3) | 3 | 3 |
| JSON-first / no-PyYAML (J1-J2) | 2 | 2 |
| runbook sentence pins (R1-R3) | 3 | 3 |
Totals: 18 mutants, 18 killed, 0 survived (6+4+3+2+3 = 18).

## Not verified
Linux/GX10 run and CI on this head; the first 10 commits' behaviours were not re-mutated (identical patches to the previously reviewed original; I relied on that, plus the suite passing).
