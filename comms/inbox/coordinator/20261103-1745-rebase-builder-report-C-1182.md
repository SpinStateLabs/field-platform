# Report: C-1182 (Lane R). Draft PR 469, head 13d8df5473fb5c6d59b6f24a7f5c21953a674a8b. Author "needs review"; not reviewed, not run on the GX10, CI not yet seen.

PR: https://github.com/SpinStateLabs/field-platform/pull/469 (draft), branch `fix/c1182-trust-env-pair-clients`. Change commit `0e7221247449c7af32a93e09a304c98dcf5077ad`, then a merge of main `cddca526`. Both commits Don Hagell noreply as author and committer.

## What changed (3 files, 89 insertions, 4 deletions against main cddca526)
- `packages/field-core/src/field_core/clients.py`: `LedgerClient` and `RegistryClient` pass `trust_env=False` when they build their own `httpx.Client` (lines 290 and 373 on main 6385f877).
- `tools/tests/http_env_proxy_allowlist.txt`: the two entries for those sites removed. The C-57 lint requires this once a site is fixed ("the list only shrinks"); no entry added.
- `packages/field-core/tests/test_clients_trust_env_c1182.py`: 4 tests. Proxy variables point at a local listener, the client's own `httpx.Client` sends one request to a second local listener, only the second may see it; plus `trust_env is False` on the client object. Loopback only.

## Measured (Windows, repo venv, relative PYTHONPATH, PYTHONUTF8=1)
- Fail-first: 4 of 4 new tests failed on main 6385f877 (HIGH, run).
- With the change: new tests plus `tools/tests/test_http_env_proxy_lint_c57.py`, 105 passed (HIGH, run).
- `packages/field-core/tests`: 1544 passed, 2 skipped, 331 s (HIGH, run).
- Main moved to cddca526 (PR 461, runbook doc) after those runs; I merged it and did NOT re-run. The diff against cddca526 is exactly the 3 files above (HIGH, git diff --stat).

## Not done / uncertain
- GX10 16-suite and CI: not run or not seen. A reviewer should confirm CI 7/7 on 13d8df54.
- The card text and the source note disagree on what "F5" is: 20261102-2130-reviewer-c1150.md F5 is the lifecycle CLI ledger table; the card describes the clients.py finding. I worked the card as written. The lifecycle CLI part is C-1171 (344/425 rebuild) and is untouched.
- I tested the two clients built here. An injected client is the caller's own and is out of scope for this card. Other pair-bearing client sites outside field-core are C-1179 to C-1181 (Lane 12, Lane 11).
- Error on my side: the first commit attempt aborted on an empty message (heredoc), and the first push put a branch equal to main on origin for a few minutes; no PR existed then. Fixed by a message file and a fast-forward push.
- My earlier C-1177 claim was not pushed (Lane 1 claimed first); stood down.

Held: C-1174 (R4b) and C-1147, as before.
