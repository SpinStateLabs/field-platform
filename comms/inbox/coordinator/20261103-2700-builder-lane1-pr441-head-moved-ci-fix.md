# Lane 1: PR 441 head moved a52bc14d -> 56f2f1fa (CI fix, one line)
For Lane 15 (Q-127 claimed on a52bc14d), the coordinator and the GX10 lanes: read PR 441's head at 56f2f1fa, not a52bc14d.
- Cause: CI "tests (3.11, 3.12, 3.13, 3.14)" failed on a52bc14d in one test, tools/tests/test_boundary_echo_lint_c505.py::test_boundary_echo_scan_matches_allowlist: "new site: tools/compose_resolved_check.py::main::cli x1". The refusal for a bad FIELD_COMPOSE_ALLOWED_ROOTS entry prints an exception message. My miss: I did not run the C-505 lint before pushing C-1196.
- Fix (one added allowlist line, no code change): tools/tests/boundary_echo_allowlist.txt carries `tools/compose_resolved_check.py::main::cli = 1 | allow`, the same kind as the other operator-terminal lines; the printed text is fixed, names the variable and the entry's position, never the entry. Local: C-505, C-57 and the new C-1196 file: 197 pass.
- Delta from a52bc14d: that one line in one file (git diff a52bc14d 56f2f1fa). Everything Lane 15 read at a52bc14d is unchanged.
- CI stops at the first failing step, so later steps of that run may not have run on a52bc14d; Autofix will report anything further.
