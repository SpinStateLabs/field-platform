# Q-90 read of PR 444, head 9e514a6ed7037415b24a20f3de21cd3fd4cd8168 (git ls-remote refs/pull/444/head agrees)

Reader: grooming assistant, not the author (Lane 1 per its report 20261102-2100-builder-lane1-c1143-report.md). READ, NOT MEASURED: nothing was run. I read the patches of services/lifecycle-manager cli.py and api.py and the first lines of tools/tests/http_env_proxy_allowlist.txt; I did not read the two test files (+232, +397), the README or the runbook patch, and I did not compare the rebuild to PRs 344 and 425 commit by commit. HIGH CARE card: a read, not a verdict.

Findings
1. HIGH (read): the one conflict in `_service_client` is resolved as Lane 1 states: the client is built with `trust_env=False`, `follow_redirects=False` and `verify=verify`, and the guarded auth object still gets (base, pair, the service's GUARDED_ROUTES). The comment names C-575, C-1041 and C-1098.
2. HIGH (read): the new `_verify_from(cacert)` returns the system store (True) when no bundle is given, or a context built from ONLY the bundle; it never returns False, and a bad file is refused with the exception type name and "nothing sent", without echoing the path or the content. `--cacert` is added to sweep, provision and decommission and passed through `estate_clients` and `_provision_clients`.
3. HIGH (read): the PR does not touch docs/ENVIRONMENT.md. The one api.py edit is a docstring at about line 180; the lifecycle_manager/api.py anchors in ENVIRONMENT.md at this head are lines 69 and 70, above the edit, so no anchor moves.
4. MEDIUM (read): the lint allowlist gains a long comment block saying the `serve` verb still reads the proxy environment through field-core's own-client mode (four serve clients, not two). So this PR fixes the CLI verbs only, not `serve`; that is stated in the file, not hidden.
5. LOW, I do not know: `--cacert` uses typer's `exists=True`; click's own message for a missing path may print the path the operator typed. That is the operator's own input, but the "no echo" rule in point 2 covers only the bad-PEM branch.
6. CI when I looked: tests (3.11 to 3.14) in_progress; compose-smoke, fly-image-smoke and compose-upgrade-smoke success. I do not know the test result.

Not checked (I do not know): the test bodies, whether patch-ids match the old heads (Lane 1 says 186998a7 matches and three commits differ only in allowlist context lines; I did not re-run `git patch-id`), and the CI test jobs. Result: no defect found in what I read; not a PASS.
