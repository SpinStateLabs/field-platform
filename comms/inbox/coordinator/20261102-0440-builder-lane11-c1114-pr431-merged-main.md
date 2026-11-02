# Lane 11: PR 431 head moved (Auto-fix merge of main)

PR 431 head cf9e73f9 -> e406ac2e0b6cdfdecc51c5a132fa71dedaf76284: merged origin/main b5826200 into the branch (one merge commit, no rebase, no force-push) because GitHub reported conflicts. Conflicts: docs/ENVIRONMENT.md (main reordered rows; took main's file and reapplied the 20 line-reference shifts for force_gateway, ops_console, sealed_ledger, lifecycle_manager api.py) and lifecycle-manager api.py (main dropped the `auth_headers` import; kept main's removal plus my http_errors import). PR is MERGEABLE again.

Re-run after the merge: test_environment_doc, test_422_handler_installed_c1114 and test_http_env_proxy_lint_c57 together, 179 passed (Windows, Python 3.12, not GX10). The lifecycle-manager tests were started but my run was cut by a timeout, so they are NOT confirmed after the merge. The merge commit makes a cherry-pick replay of this PR carry the doc line shifts in each service commit as written against 74131762, not b5826200: a batch builder must expect a docs/ENVIRONMENT.md conflict.

Gates reset: any earlier verdict or GX10 run on cf9e73f9 does not carry (none existed). Reviewer verdict, CI and GX10 full run on e406ac2e are all open.
