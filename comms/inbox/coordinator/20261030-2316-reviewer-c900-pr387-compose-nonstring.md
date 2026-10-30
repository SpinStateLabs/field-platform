VERDICT: PASS WITH CONDITIONS on d4902a0fff7c49bd36943d82249aeb6acfba1d13

Reviewer Lane 15, cloud-reviewer, C-900, PR 387. UNVERIFIED: no GX10, CI not read; scratch-tree probes and mutants only.

## Objections first
1. Premise: PR 387 does not close "the C-640, C-648 and C-765 conditions on PR 345". It closes ONE, C-765 F-C765-1, and only the top-level half (named-volume device, secret and config file) plus a comment on the docker.sock line. The service-level half is in earlier stacked commits (783a85f..112cf16). The other C-640/C-648 findings are neither addressed nor claimed by this PR (HIGH).
2. PR 387 is a tests-and-pins change in the static layer only: `tools/tests/test_compose_static_pins.py:452-466` (new block in key_violations). It does not touch the resolved check.
3. Open and unchanged, so the "class closed" claim still fails: the resolved-layer tmpfs exemption (`tools/compose_resolved_check.py:171-172`, the type-tmpfs-or-device-tmpfs skip; C-648 F-C648-8 turned into a bypass, probed earlier under C-899); the static key_violations accepts, with no violation, a split-default caller-key path (C-640 F-C640-4), an `https` additional context and a variable-defaulted remote context (C-640 F-C640-1). Whether the rest of check_compose refuses those three I could not establish: my full-document probes stopped at an unrelated hardening assertion (no-new-privileges) before reaching the path rules. Treat as MEDIUM, not proven (not verified).
4. Mutant survivors: none attributable to the new code except the docker.sock assertion, which the PR keeps on purpose and documents (equivalent mutant, C-765 F-C765-3; condition C2 met by "keep knowingly").

## C-765 conditions
- C1 non-string path carriers refused, env_file TypeError turned into a finding: CLOSED for all eight positions I probed (bind source list and int, env_file int and nested list, build.context list, dockerfile int, additional_contexts list, build as a list; each reported "not a string", each also refused by check_compose, no exception) and for top-level device, secret file, config file. A top-level section of unknown shape (driver_opts list, non-mapping) is reported, not raised (HIGH).
- C2 redundant docker.sock check: kept knowingly, comment at test_compose_static_pins.py:502-503. CLOSED.
- C3 keep the resolved check on the gate: not in this PR's scope; still true (unwired status of that tool is C-648 F-C648-4, not re-checked here).

## C-640 / C-648 (this PR vs. the whole stack)
- C-640 F-C640-5 non-string sources: CLOSED by this PR plus 5d5cbf7/1381b56/e57632f. F-C640-2 case drift (.GIT, .ENV in the resolved layer): CLOSED, probed (both refused). F-C640-3 survivors volumes_from, ipc, userns_mode, cgroup: refused (probed). F-C640-6: pid and ipc now refused by the resolved layer; an `extends` key still returns no problem there (probed). F-C640-1 and -4: see objection 3.
- C-648 F-2 dockerfile, F-1 scheme contexts: refused in the resolved layer (probed, absolute dockerfile and oci-layout). F-7 empty service map: ValueError (exit 3). F-8: the tmpfs exemption is the "fix"; see objection 3. F-3 profiles and F-4 wiring: not re-checked.

## Evidence
- 791 tests pass in test_compose_static_pins.py plus the new test_compose_static_nonstring_c817.py (22 tests) (HIGH).
- Mutants on the new code: 7 real mutants, all killed (device check off, file check off, secrets-only, handler narrowed, device key renamed, file key renamed); docker.sock assertion off survives, equivalent as stated. One no-op mutant discarded. Files restored; worktrees removed.
- Commit identity guard: clean (8 commits). merge-tree against origin/main: clean.
- Relation: stacked on PR 385 (112cf16), so on 370 and 353; merge after them. PR 345's own commits (7679259, f3787c9) are inside this stack.

## Conditions
1. Do not describe the stack as closing C-640/C-648 wholesale: state F-C640-1/-4/-6 (extends) and F-C648-8/-3/-4 as open or fixed. Non-blocking for the merge, blocking for the wording.
2. Run check_compose on a fully hardened fixture with a split-default key path and a remote context to settle objection 3. Non-blocking.
3. Merge order 353, 370, 385, 387.

Not verified: GX10, CI, compose itself, F-C648-3/-4, objection 3 at check_compose level.
