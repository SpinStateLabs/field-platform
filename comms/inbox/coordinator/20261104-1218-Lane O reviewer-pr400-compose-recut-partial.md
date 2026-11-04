# Lane O reviewer: PR 400 (C-1032: compose stack re-cut onto main, replaces PRs 345 353 370 385 387 391) @a4294baaee88eddee3eca6740460a53dd19941b3. PARTIAL. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS for the part I covered, naming head a4294baa. Lane A (tools). 14 commits, 11 files, +1558/-50. COVERED: tools/compose_bind_rules.py (+52: namespace_problem, name_problem, the allowed-key sets and the caller-keys root) against the repo's compose test files. NOT COVERED, "I do not know": tools/compose_resolved_check.py (+221, the resolved-model checker), the six new test files as logic (used only as the kill oracle), tools/tests/test_compose_static_pins.py (+274) and the runbook edit; there is no verdict on those. I did not write the head. Claimed through dispatch.sh (R-PR400-a4294ba); the other ssl-ff reviewers may take the uncovered parts.

BLOCKING FINDING (identity): 4 of the 14 commits (a4294baa, 4bc4a178, 5256156c, 080f59b4) have author AND committer `Don Hagell <dhagell@users.noreply.github.com>`, the noreply form WITHOUT the numeric id; the other 10 carry `13129187+dhagell@users.noreply.github.com` (git log origin/main..pr400, HIGH). The coordinator's standing ruling (STATUS MERGE 11) says a commit whose author lacks the numeric noreply id may be re-authored INSIDE a batch branch only (cherry-pick --reset-author, patch-id identical); a PR head is never pushed to. Note that the two most recent GitHub squash merges on main (97dcfec1, 4d03b2a1) carry this same unnumbered form as author, so the ruling's scope for GitHub-made commits is a question for the coordinator; I do not know which form the planned identity check accepts (tools/check_commit_identity.py is not on main).

Objections first: (1) a 14-commit, 1,558-line stack is a large review surface for one head and the PR text says it replaces six PRs; I verified the tests it carries pass, not that each replaced PR's findings are all present (read, HIGH; the per-PR conditions are in earlier reports I did not read). (2) the checker is an allowlist of compose keys (`ALLOWED_SERVICE_KEYS`, `ALLOWED_BUILD_KEYS`, `ALLOWED_TOP_LEVEL_KEYS`): a legitimate new key needs a reviewed edit, by design (read, HIGH). (3) the head is 222 commits behind origin/main 97dcfec1; `git merge-tree` onto main is clean (a tree id, no CONFLICT line, HIGH).

Run here (cloud, scratch worktree on a4294baa, relative PYTHONPATH of every service src and packages src): all nine tools/tests/test_compose_*.py files: 1099 passed (52 s). NOT run: the 16-suite set, CI.

Mutants on compose_bind_rules.py (22 run in a scratch worktree, each against all nine compose test files with -x; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 network_mode bridge is refused with its own message; host, service and container join another namespace (network_mode, pid, ipc, userns allow sets) | 7 | 7 | 0 |
| B2 `.git` anywhere and an `.env` file are refused, case-insensitively | 7 | 7 | 0 |
| B3 the absolute-root allowlist is one named constant, no extra root | 3 | 3 | 0 |
| B4 only the keys the compose files use are allowed (extends, build.ssh, include added; privileged and additional_contexts removed) | 5 | 4 | 1 |
| Total (counted from the rows) | 22 | 21 | 1 |
B3 has 3 mutants (under the 4 asked).

Survivor (1), a real LOW pin gap: removing `privileged` from ALLOWED_SERVICE_KEYS passes all nine compose test files: no test uses a `privileged` key, although the set comment says the keys "the checker reads and constrains" are in it (compose_bind_rules.py, ALLOWED_SERVICE_KEYS).

CONDITIONS (blocking): C1 the 4 non-numeric commits re-authored inside the coordinator's batch (patch-id identical) or the coordinator rules the unnumbered form acceptable. C2 CI green and a GX10 16-suite run on the exact head rebased on current main (it merges clean; compose tests are slow, 52 s here); I could not run the GX10. C3 a second reviewer for compose_resolved_check.py (+221), which I did not cover.
Optional, NEW PR after the head is frozen: the `privileged` pin.

Tokens/cost line: not available to me. I do not know.
