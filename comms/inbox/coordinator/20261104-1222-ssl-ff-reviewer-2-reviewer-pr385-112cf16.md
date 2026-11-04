# Reviewer report: PR 385 @112cf16d (compose resolved check: realpath roots and text checks, C-823, PR 353 conditions)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. Re-claimed after my earlier release; I reviewed only what the head claims: the C-823 delta (top two commits, tools/compose_resolved_check.py and tools/tests/test_compose_pr353_conditions_c823.py). The commits below them are the C-512, C-638 and C-715 stack.

## Verdict: PASS WITH CONDITIONS (head 112cf16d3328fc431c106d75f8e6d834a8ee2ef6)
Conditions: C1 REBUILD on main. The GitHub base is branch `test/compose-pr345-conditions-c715`; `git merge-tree` against main 97dcfec1 reports add/add conflicts in tools/tests/test_compose_resolved_bind_c512.py and a content conflict in tools/tests/test_compose_static_pins.py, because main already carries an earlier tools/compose_resolved_check.py and tools/compose_bind_rules.py (and PR 441 changes both again: the allowed-roots variable). The C-638/C-715/C-823 conditions are not on main, so the rebuild must re-apply them over main's version, and PR 441's `allowed_absolute_roots()` must be combined with this head's `roots` logic (see objection 2). C2 GX10 16/16 and CI green on that rebuilt head. No defect in the C-823 code itself.

## Objections first
1. On its own the head is self-consistent: the five compose test files 1023 passed (HIGH, run). The risk is entirely in the merge, not the code.
2. Interaction with PR 441: this head's `source_problem` builds `roots = list(ALLOWED_ABSOLUTE_ROOTS)` (new) while 441 replaced the iteration with `allowed_absolute_roots()`. Merged naively, one of the two edits is lost: either the estate's variable roots or the realpath-resolved roots stop being honoured (HIGH that both edit that line; the merge outcome is not run).
3. `--realpath` resolves from the string as written, so a `..` after a symlink is followed physically; the lexical form is judged first, then the resolved form, and both must clear the denylist (pinned P1, P2) (HIGH, run).
4. The posture limit is stated in the docstring: `cap_add`, `cap_drop`, `security_opt`, `ports`, `user`, `sysctls`, `ulimits` are NOT judged by the resolved check (read of the diff). That is an acknowledged hole, not covered by any test and not closed here (HIGH).
5. The mutants edit one file under test on a POSIX host; the tests skip when symlinks are unavailable (`link()` skips), so on a host without symlink rights the realpath behaviours are not exercised at all (HIGH, read).

## Scope and identity
7 files in the stack, +1532/-29; the C-823 delta is two files. 7 commits; author AND committer on all seven = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py` is absent at this base, not run.

## Runs
Baseline (unmutated head): test_compose_pr353_conditions_c823.py 41 passed; with the C-715, C-638, C-512 and static-pin files 1023 passed. Mutants edit tools/compose_resolved_check.py one at a time; kill = the C-823 file fails; for the survivor I also ran the other four compose files; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| P1 | realpath as written | resolves the normalised path, not the string | KILLED |
| P2 | realpath as written | denylist not re-applied after resolution | KILLED |
| P3 | realpath as written | no resolution at all | KILLED |
| P4 | roots resolved | allowed roots not resolved | KILLED |
| P5 | roots resolved | declared spelling of the roots no longer allowed (roots = []) | KILLED |
| P6 | roots resolved | only resolved roots (declared spelling dropped under realpath) | SURVIVED (also by the other four compose files: 982 passed) |
| N1 | non-mapping service | skipped | KILLED |
| N2 | non-mapping service | check removed | KILLED |
| E1 | env_file shape | shape error removed | KILLED |
| E2 | env_file shape | non-string path skipped | KILLED |
| T1 | text check | driver_opts.device not text-checked | KILLED |
| T2 | text check | secret and config file not text-checked | KILLED |
| T3 | text check | env_file not text-checked | KILLED |
| T4 | text check | build.context not text-checked | KILLED |
| T5 | text check | build without a context key judged as None | KILLED |
| S1 | script path | abspath, not realpath (symlinked script) | KILLED |

Counted from the table: 16 rows (realpath 3, roots 3, non-mapping 2, env_file 2, text check 5, script path 1). KILLED 15, SURVIVED 1, none equivalent. Kill rate 15 of 16 = 94%. Per behaviour: realpath 3/3, roots 2/3, non-mapping 2/2, env_file 2/2, text check 5/5, script path 1/1.

## Findings
- F1 LOW (HIGH confidence, run): P6. The comment in source_problem says "the declared spelling stays allowed too"; no test fails when only the resolved spelling is kept. Add a case where the declared root is not a link.
- F2 MEDIUM for the merge (HIGH it is a hazard, not run): objection 2, the PR 441 collision.
- F3 LOW: objection 4, the unjudged hardening keys remain an open item.

## Not verified
The rebuilt head; CI; GX10; PR 441 plus this head merged; behaviour on a host without symlink permission; the C-512, C-638, C-715 commits beneath the delta.
