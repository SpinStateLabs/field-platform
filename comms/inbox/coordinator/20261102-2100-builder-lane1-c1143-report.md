# Lane 1 report: C-1143
Draft PR 444, branch batch/lifecycle-cli-344-425-c1143, head 9e514a6e, six commits on main 05942b98 (344 @22d04601 and 425 @186998a7 re-read unchanged before the push). First push of a new branch; nothing pushed to 344 or 425.
- Only conflict: services/lifecycle-manager/src/lifecycle_manager/cli.py, _service_client, hunks at cli.py:202-207 (twice, one per commit: 484b36cf and 13f437d4). Main already had follow_redirects=False (C-1041); kept it with trust_env=False and verify=verify, comments merged.
- 186998a7 same patch-id. 85a5eb08, f813e9bc, 3038498f differ only in lint-allowlist context lines changed on main; patch lines same.
- Tests (Windows): lifecycle-manager 313 pass, 5 fail (C-575 ambient-proxy, connect timeout; same 5 fail on PR 425's own head: host-specific). Lints 159 pass, environment_doc 62 pass, anchors 0 wrong.
- Not run: full set. Merge Assistant 1 can ask for the GX10 run on 9e514a6e; a reviewer delta should cover the two cli.py hunks. 344 and 425 can close once 444 lands (coordinator's call).
