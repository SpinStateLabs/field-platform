# Reviewer report: PR 441 @56f2f1fa (scrub the estate home-path account name; configurable bind roots FIELD_COMPOSE_ALLOWED_ROOTS, C-1132, C-1133, C-1196)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. Deploy-gate rules (what a compose bind may mount) and a public-safety scrub.

## Verdict: PASS WITH CONDITIONS (head 56f2f1fa35a5e2ddd6c2c2469732e7c83922e0d7)
Conditions: C1 rebase on current main: the head sits on 05942b98; STATUS (MERGE 23 and 24) says "PR 441 ... must be rebuilt on cd3b7690"; `git merge-tree` of main 97dcfec1 with this head shows no textual conflict, but the scrub touches 16 files and main moved 8 merges, so a rebased run is needed. C2 GX10 16/16 on the exact rebased head; C3 CI green. C4 (public repo) the coordinator confirms the scrub list: I found zero remaining hits for the old account name's string in the head (`git grep` of the name seen in the diff's removed lines returned nothing), but I cannot know every spelling the estate used; the scrub's own card (C-1132, C-1133) defines the set. No blocking code finding.

## Objections first
1. The new deploy-time variable widens a security rule from environment: whoever sets FIELD_COMPOSE_ALLOWED_ROOTS adds an allowed bind root. The guard is the denylist inside `_root_problem` (system trees, home dirs, runtime sockets, relative and dot segments, `$` and backtick). Of those, the runtime-socket branch has no pin (F13 survives the PR's tests and the 941-test tools set) (HIGH, run).
2. An allowed root such as `/data` (not on the denylist) permits any descendant mount, including a descendant that is itself a credential directory the denylist does not know about. The design rests on the estate choosing narrow roots; the code cannot judge that (HIGH, reasoned from `_root_problem`).
3. The static pins ignore the variable by design ("The static pins ignore it"); an estate that relies on the variable passes only the resolved check, and the pins still judge the committed placeholder (HIGH, read and pinned by test_the_committed_constant_is_not_changed_by_the_variable).
4. The refusal message names the variable and the entry position and prints it to stdout, so a bad entry's text is not echoed (pinned by F15/F17/M3 below). The boundary-echo allowlist gets one new line for `tools/compose_resolved_check.py::main::cli` (HIGH, read).
5. The PR bundles a repo-wide scrub (12 files of docs and config) with new code; a scrub that rewrites runbooks can change documented commands. The deploy-docs, static-pins and mounts tests pass (941 passed, below) (HIGH).
6. `docs/ENVIRONMENT.md` gains a section "Variables read by tools/"; the env-doc test is satisfied because the section lists the variable outside the checked table (HIGH, test_environment_doc passes).

## Scope and identity
16 files, +295/-108, 4 commits; author AND committer on all four = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). Every path in the new test is a made-up `/data/example-field/...` (HIGH, read).

## Runs
Baseline (unmutated head): new test file tools/tests/test_compose_allowed_roots_env_c1196.py 38 passed. Broader set (that file plus test_compose_resolved_bind_c512, test_compose_static_pins, test_deploy_docs, test_operator_mounts_b6, test_boundary_echo_lint_c505, test_environment_doc) 941 passed, with all service `src` dirs, field-agent `src` and `tools` on a relative-from-root PYTHONPATH (without them 9 tests fail with ModuleNotFoundError; the same test fails on base 05942b98 in my environment, so that is my environment, not the PR). Mutants edit tools/compose_bind_rules.py and compose_resolved_check.py one at a time; kill = the new test file fails; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| E1 | env default | variable renamed | KILLED |
| E2 | env default | entries not stripped | KILLED |
| E3 | env default | empty entries not skipped | KILLED |
| E4 | env default | default roots dropped | KILLED |
| E5 | env default | non-empty fallback value | KILLED |
| A1 | adds roots | duplicates kept | KILLED |
| A2 | adds roots | trailing slash kept | KILLED |
| A3 | adds roots | added root inserted before the default | KILLED |
| A4 | adds roots | only one added root | KILLED |
| F1 | fail closed | relative path accepted | KILLED |
| F2 | fail closed | `$` accepted | KILLED |
| F3 | fail closed | backtick accepted | KILLED |
| F4 | fail closed | newline accepted | KILLED |
| F5 | fail closed | carriage return accepted | SURVIVED (LOW, F2) |
| F6 | fail closed | dot-dot accepted | KILLED |
| F7 | fail closed | empty and dot segments accepted | KILLED |
| F8 | fail closed | exact-forbidden list dropped | KILLED |
| F9 | fail closed | A_HOME dropped | KILLED |
| F10 | fail closed | home parents dropped | KILLED |
| F11 | fail closed | forbidden trees dropped | KILLED |
| F12 | fail closed | home credential dirs dropped | KILLED |
| F13 | fail closed | runtime sockets accepted | SURVIVED (also survives the 941-test set; F1) |
| F14 | fail closed | tree itself allowed | KILLED |
| F15 | fail closed | message echoes the entry | KILLED |
| F16 | fail closed | message omits the variable name | KILLED |
| F17 | fail closed | message appends the entry | KILLED |
| F18 | fail closed | validation skipped | KILLED |
| U1 | resolved check | variable ignored by source_problem | KILLED |
| U2 | resolved check | root itself and prefix siblings allowed | KILLED |
| U3 | resolved check | only the first root honoured | KILLED |
| M1 | cli | bad variable not checked in main | KILLED |
| M2 | cli | exit 1 instead of 2 | KILLED |
| M3 | cli | main prints the variable value | KILLED (my mutant referenced `os` without an import in that module, so it may have died on a NameError rather than on the assertion; treat as MEDIUM confidence) |
| D1 | scrub | default root not the example placeholder | KILLED |

Counted from the table: 34 rows (env default 5, adds roots 4, fail closed 18, resolved check 3, cli 3, scrub 1). KILLED 32, SURVIVED 2, none equivalent. Kill rate 32 of 34 = 94%. Per behaviour: env default 5/5, adds roots 4/4, fail closed 16/18, resolved check 3/3, cli 3/3, scrub 1/1.

## Findings
- F1 MEDIUM (HIGH confidence, run): F13. A runtime-socket entry such as `/data/x/docker.sock` is accepted if the branch is removed; the guard against mounting a container-runtime socket through the new variable is unpinned. Add `"/data/example-field/docker.sock"` to the refused-entries parametrisation (condition fix: one list item).
- F2 LOW: F5, a bare carriage return is unpinned (a newline is).
- F3 LOW: objection 2 is a design limit, not a defect; the ENVIRONMENT.md paragraph says "no real path belongs in the repository" and should add "choose the narrowest directory".

## Not verified
Rebase on 97dcfec1; CI; GX10; the completeness of the scrub against the card's definition; that the 12 scrubbed doc and config files keep every command working (the deploy-docs and static-pin tests pass, which covers what they cover).
