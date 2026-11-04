# main is red: C-57 proxy lint flags tools/start_role_session.py (from PR 532)

From: ssl-fp-docs agent (cloud session field-platform-b8). Sent at Don's instruction.

## Finding
- `tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist` fails on main since 4d03b2a (PR 532, "tools: add start_role_session.py and role-agent team access doc").
- Message: `new unproxied-env client (pass trust_env=False / ProxyHandler({})): tools/start_role_session.py::call::urllib.request.urlopen x1`.
- Evidence: CI run 41812420379 on PR 539, `tests (3.11)`, `(3.12)` and `(3.13)` each 1 failed, 3800 passed, 4 skipped (`tests (3.14)` not read). Reproduced locally on `origin/main` (1 failed in 3.34 s). Not caused by PR 539, which changes docs only.
- Effect: every PR's `tests` jobs fail on this assertion until it is fixed. A fast-forward merge rule that needs green CI is blocked for all PRs.
- Why it is not noise: `call()` sends `x-api-key: $ANTHROPIC_API_KEY` through `urllib.request.urlopen`, which honours HTTP_PROXY / HTTPS_PROXY. The C-57 rule exists so an environment proxy never receives the key.

## Proposed fix (not applied; code change, outside the docs lane)
- In `tools/start_role_session.py`, open the request with `urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60)`, or add a reasoned allowlist entry. The owner chooses. A builder card is needed: no open PR or WORKLIST item names `start_role_session` (checked 2026-11-04).

## Related, same commit
- `docs/ROLE-AGENTS-TEAM-ACCESS.md` and the script publish a workspace id, an environment id and five agent ids in a public repository. PROTOCOL.md's public-files rule names no ids; a ruling is needed. I believe they are not credentials (MEDIUM). Not edited.
- Recorded in docs/DOSSIER.md and CHANGELOG.md on PR 539 (draft, CI red from this failure only).

## Also still open from my earlier note
- PR 520 was merged by this session on Don's instruction without reviewer PASS or CI. Post-merge check on main is still requested.
