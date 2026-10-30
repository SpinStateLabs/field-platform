VERDICT: C-732 PASS WITH FINDINGS on fd377edb4e963cdcca78826fa583716d7cebf405 (PR 344, a second commit on 005ba2b). F-C639-1 is pinned as stated: the CLI's estate clients read no proxy variable and follow no redirect (observed against a listener standing in for a proxy), and 8 of 10 own mutants go red. F-C639-2 stays open exactly as the builder says: the `serve` verb's field-core clients still read the proxy environment (observed). Covers C-742 (see 20261105-0230-design-c742-coverage.md). UNVERIFIED on any estate; cloud container only.

## Objections first
1. THE `serve` CLIENTS STILL USE THE PROXY ENVIRONMENT, OBSERVED. With HTTP_PROXY, http_proxy and ALL_PROXY pointing at a local listener and made-up service URLs, `RegistryClient().get_agent("a")` and `LedgerClient().events()` (the own-client mode used by `serve`, lifecycle_manager/cli.py:469 and api.py:147, 149, 408, 410) each made one connection to the listener; every one of the six CLI estate clients (`estate_clients`) made none. The two construction sites are `packages/field-core/src/field_core/clients.py:275` and `:358` (`httpx.Client(timeout=5.0)`), allowlisted with a note that explains the dependency on C-487 (tools/tests/http_env_proxy_allowlist.txt, the new header). What travels on those clients: the perimeter secret and, for the ledger client, the pair on a guarded write. HIGH (observed). This is the answer to the card's "any client still reading trust_env": two, both named, both known.
2. THE ALLOWLIST NOTE ARGUES THAT NO SMALL FIX EXISTS. "An injected client must carry its own auth headers (the field-core clients add none then)". PR 330's `PerRequestAuthClient` (a client that adds the headers per request) is a candidate for that role, and PR 330's own `build_request` decides the pair on the wire path; whether `serve` can adopt it is C-487's question, not this PR's. MEDIUM.
3. TWO SURVIVORS IN MY MUTANTS. (a) `follow_redirects=False` removed (cli.py:196-197): survives, because False is httpx's default; the new test docstring says so and calls it "a pin", but nothing fails if httpx's default changed, since the test would observe whatever the mutant leaves. The True mutant is killed (13 failed). LOW. (b) the governor client's `timeout` argument ignored: survives (the timeout is unpinned). LOW.
4. `trust_env=False` ALSO REMOVES `SSL_CERT_FILE`, `SSL_CERT_DIR` AND `.netrc` FOR THESE CLIENTS. The commit states it (README, test docstring; the builder says verified in httpx 0.28.1; I did not re-verify). Consequence stated by the README: an https estate behind a private CA needs `verify=` in code, not an environment variable. A deployment that relied on SSL_CERT_FILE for the CLI would now fail certificate checks (fail-closed). MEDIUM (reasoned; not run against a private CA).
5. THE README CLAIM "READ NO PROXY VARIABLE" COVERS THE CLI VERBS AND `sweep` ONLY (README line added by fd377ed); the `serve` exception is stated in the same paragraph. Accurate. HIGH.

## What changed since the C-639 note (the C-742 question)
fd377ed adds tests (the file grows from 10 to 20 tests), a README paragraph, and a 5-line header on the lint allowlist; no production code (the one production change, the two arguments in `_service_client`, is in 005ba2b). It adds no behaviour beyond the C-639 note. HIGH (read: `git show HEAD --stat`: README +6, test +46, allowlist +5).

## Steelman
`_service_client` is the single place the CLI builds an estate client (cli.py:191-197) and every entry in `estate_clients` goes through it, except the two field-core wrappers which receive an injected client built by it. My mutants that bypass it for any service (raw client for delegation or killswitch, a wrapper in own-client mode, perimeter headers or guarded auth removed, `trust_env` removed or `follow_redirects` True, base URL dropped) all fail 4 to 13 tests. `_provision_clients` returns `estate_clients(pair)` (cli.py:~219-221), so it cannot diverge.

## Mutants (20 tests pass unmutated; file restored after each)
| Mutant | Result |
|---|---|
| trust_env=False removed | 13 failed |
| follow_redirects=False removed | SURVIVES (httpx default; see 3a) |
| follow_redirects=True | 13 failed |
| perimeter headers removed; guarded auth removed | 8 failed each |
| registry or ledger wrapper in own-client mode | 4 failed each |
| delegation or killswitch client a raw httpx.Client | 4 failed each |
| governor timeout ignored | SURVIVES |
| base_url dropped | 10 failed |
HIGH (observed). The builder's six reviewer survivors (M06, M09, M10, M11, M14, M20) were not available to me by those names; my set overlaps in intent. Merge-tree with PR 318 and with PR 330: clean (observed).

## What I did NOT do
- No GX10 or estate run; the whole lifecycle-manager and tools suites were not run on this head (I ran the C-575 file, 20 passed, and the lint file, 21 passed).
- Did not verify the httpx 0.28.1 statement about SSL_CERT_FILE and `.netrc`.
- Did not read the `sweep` verb's code path separately.
