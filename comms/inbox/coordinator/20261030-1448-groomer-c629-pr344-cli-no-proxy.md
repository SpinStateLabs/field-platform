# C-629 cloud read of PR 344 at head 005ba2b (Lane 9, UNVERIFIED: no GX10, nothing run; static read of the diff and tree)

VERDICT: the CLI fix is correct for the one client it touches. It leaves two other client paths in the same service reading the proxy environment, and the C-57 lint cannot see them.

OBJECTIONS FIRST
1. "Every httpx client in the CLI path" is not "every client in the lifecycle-manager". The `serve` verb builds the app, which builds clients elsewhere.
2. The lint is scoped to calls spelled `httpx.<Client|...>`; a subclass is not such a call.
3. Removing an allowlist line only proves that one call now passes; it says nothing about code the scan cannot see.

ASSUMPTIONS: head 005ba2b is what PR 344 shows (ls-remote refs/pull/344/head, HIGH). httpx's default is follow_redirects=False and trust_env=True (general knowledge, HIGH).

FINDINGS
- F-C629-1 MEDIUM (HIGH confidence it is unguarded): services/lifecycle-manager/src/lifecycle_manager/api.py:87 `class PerRequestAuthClient(httpx.Client)`, built at api.py:117 (`delegation_client`) and api.py:128 (`killswitch_client`). No trust_env=False, so an ambient HTTP(S)_PROXY routes these. Their docstring says they send `auth_headers()` on every request: the shared secret and the operator pair, reads included. That is the exposure the PR's own comment (cli.py:194-195) describes for the CLI, on the `serve` path. Redirects are not followed (httpx default), so only the proxy half applies.
- F-C629-2 MEDIUM (lint blind spot): tools/tests/test_http_env_proxy_lint_c57.py visit_Call (about :80-85) matches only names starting `httpx.`; `PerRequestAuthClient(...)` and any `class X(httpx.Client)` are never counted, and the allowlist has no lifecycle-manager entry for api.py. The shrunk allowlist therefore reads as "lifecycle-manager is clean" when api.py is not. Fix options: add a ClassDef check for bases that resolve to httpx.Client/AsyncClient (counted unless the class forces trust_env=False in `__init__`), or set `trust_env=False` in the two builders and pin it.
- F-C629-3 LOW-MEDIUM: cli.py:469 `LedgerClient()` (serve path, own-client mode) reaches packages/field-core/src/field_core/clients.py:275, `httpx.Client(timeout=5.0)`, which is allowlisted (allowlist lines 14-15) and so already known to C-57. Not a PR 344 defect; noted because the PR's claim is "no estate client reads the proxy" and this one does, in the same service.
- F-C629-4 LOW: the PR's tests cover the CLI clients (test_cli_clients_no_proxy_c575.py :72-130: trust_env False, a proxy gets 0 hits, a 302 is not followed). Nothing covers api.py's builders.

WHAT I COULD NOT VERIFY: any test run, the lint run on this head, the C-57 allowlist-equals-scan check after the removal (the allowlist diff is one deleted line, which is consistent with the one fixed site).

CONCLUSION: PASS for the CLI change as scoped. Do not read it as closing C-524 F-C524-2 for the service: file one builder card for api.py:117/:128 plus the lint subclass gap (F-C629-1/-2).
