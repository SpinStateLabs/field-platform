VERDICT: PASS WITH CONDITIONS on b47ee05cd97947aebd738cd26c2406bcf1de9ca3

Card C-462, PR 295 (C-57, tests only: tools/tests/test_http_env_proxy_lint_c57.py new, tools/tests/http_env_proxy_allowlist.txt new), Lane 7. Head confirmed by PR read: b47ee05, one commit. The card says main 3ee2e5d; main is now 48acfa6 (it includes PR 288); the commit cherry-picks onto 48acfa6 with no conflict. A PASS applies to this SHA only. No production file changes.

Conditions (three, none blocks a tests-only merge): (1) the "scan is not blind" test turns red exactly when the migration it exists for succeeds (F-C462-1); (2) the lint cannot see a subclassed or re-bound client, and one such client with auth headers exists today (F-C462-2); (3) six of the eleven httpx call names and the no-argument `ProxyHandler()` shape are not pinned (F-C462-3).

OBJECTIONS
1. A lint that matches call names misses a client built through another name (subclass, assignment, partial, getattr): failure condition.
2. An allowlist that "can only shrink" plus a guard that demands at least 50 sites cannot both hold: the guard fails when the allowlist shrinks below 50, or sooner when the last httpx.Client site is migrated.
3. The scan roots are a fixed list; a new top-level directory, or a file type other than Python (shell scripts with curl, node), is outside it.
4. A pinned list entry is keyed by function and call; a fix in one place and a new site in the same function of the same call nets to zero.
5. `trust_env=False` has side effects beyond the proxy variables; mass-applying it can change TLS and netrc behaviour.

ASSUMPTIONS
A1. The lint reads non-test Python under packages, services, tools, plugins, integration, defence-shield (HIGH, SCAN_ROOTS).
A2. "Matters" means: the client carries a secret (shared secret, operator pair, API key) and could send it to a proxy named in the environment.

REASONING
1. The PR's own file passes on the head: 21 passed. Whole `python -m pytest -q tools/tests` on main 48acfa6 plus this commit: 2827 passed, 7 skipped, 0 failed (745 s). CI on the exact head: 7 of 7 success (tests 3.11 to 3.14, fly-image-smoke, compose-smoke, compose-upgrade-smoke).
2. Allowlist equals the scan: my own call of the scan gives 63 sites in 58 keys, the allowlist parses to 63 sites in 58 keys, and the two Counters are equal (HIGH, run). The PR text says 58 keys and 63 sites: confirmed.
3. An empty scan fails: yes, `test_the_scan_is_not_blind` (at least 50 sites, an httpx.Client key and a urllib.request key). Not an independent control: see F-C462-1.
4. Which of the C-55 shapes matter (repo grep of non-test Python, then the scanner on each shape):
   - Re-bound or subclassed httpx client: MATTERS. `class PerRequestAuthClient(httpx.Client)` at services/lifecycle-manager/src/lifecycle_manager/api.py:87 is built at :117 (delegation_client) and :128 (killswitch_client) with no `trust_env=False`, and it adds the shared secret and the operator pair on every request (api.py:87-110). The scanner returns nothing for that file (run); the allowlist has no api.py entry (its only lifecycle entry is cli.py::_service_client). A migration that follows the allowlist to the letter leaves both clients on the proxy environment. Proven.
   - `requests`: 0 uses in non-test Python today (grep). Latent; does not matter now.
   - `http.client`: 3 files; two import it only for exception names (field_agent/field_client.py:39, field_core/alerts.py:59); tools/phase_g_check.py:99,175 opens connections directly. The standard-library `http.client` does not read proxy variables, so this is NOT a gap (general knowledge, MEDIUM-HIGH).
   - `aiohttp`: appears once, inside a user-agent regex string (defence-shield signatures.py:117); no use.
   - The Anthropic SDK client: `anthropic.Anthropic(api_key=key)` at services/claude-approver/src/claude_approver/client.py:25. It builds its own httpx client, reads the proxy environment by default, and carries the API key. Not seen by the lint. Over https a proxy sees the host, not the key, unless it intercepts TLS (MEDIUM, general knowledge); a decision for C-56, not for this PR.
   - Other shapes the scanner misses (probed): `k = httpx.Client; k()`, `functools.partial(httpx.Client, ...)`, `getattr(httpx, "Client")()`, a call that precedes a later module-level `import httpx`, `urllib.request.urlretrieve`. Flagged correctly: `from httpx import Client as C`, an import inside the function, `trust_env=<variable>` or `=0`, `install_opener(build_opener())`, a ProxyHandler built from a variable dict.
5. Mutants (hand, 37, run as copies of the test file): 24 red / 37. Survivors: HTTPX_CALLS without `AsyncClient`, `patch`, `delete`, `head`, `options`, `request` (six; the shape tests pin only Client, get, post and stream, and the repo has no such sites today); `ProxyHandler()` accepted with no argument (two mutants: the argument-count test is missing; `build_opener(ProxyHandler())` is the unsafe default and nothing pins its rejection); `from httpx import Client as C` with the alias ignored; the `defence-shield` scan root dropped (no site there today, so equivalent now, latent); `test_` filename skip dropped (equivalent today); the blind guard at threshold 0 and without the httpx.Client presence check (the guard itself is untested). Non-equivalent survivors: 11 of 13; equivalent today: 2 (the `test_` prefix and arguably the defence-shield root).
6. The migration problem, with numbers: the guard needs at least 50 sites and an `httpx.Client` key. The repo has 63 sites; migrating 14 breaks the first; migrating the last `httpx.Client` breaks the second. C-56 is the card that does this migration. So the first successful migration turns this test red, by design of the test and against the design of the PR ("the list only shrinks"). Arithmetic from the files, HIGH.
7. Fixed scan roots: the repo's non-test Python is entirely under the six listed roots (git ls-files: defence-shield 10, integration 11, packages 37, plugins 2, services 91, tools 22 files), so nothing is missed today; a new top-level directory would be (MEDIUM, no test pins it). Shell and node clients (curl, fetch) are outside the lint by construction; curl honours the proxy variables (general knowledge, MEDIUM); not examined.
8. `trust_env=False` also turns off httpx's other environment settings (the certificate variables and .netrc), not only proxies (httpx documentation, general knowledge, MEDIUM; I did not run it). A client that gets its CA through an environment variable would lose it when migrated. For card C-56, not this PR.

FINDINGS
- F-C462-1 MEDIUM-LOW, design: tools/tests/test_http_env_proxy_lint_c57.py `test_the_scan_is_not_blind` fails when the migration succeeds (reasoning 6). Fix: keep the positive control independent of the allowlist: assert the scanner over a built-in snippet (already in test_the_scanner_flags) and over a minimum number of scanned files (`python_files()` count), not over the number of remaining sites.
- F-C462-2 MEDIUM (PROVEN): subclassed and re-bound clients are invisible; services/lifecycle-manager/src/lifecycle_manager/api.py:87 (built at :117 and :128) carries the shared secret and the operator pair. Fix: add a scan for classes whose base is an httpx client (and flag their construction), or add these two sites to the allowlist by hand and a test that every `class X(httpx.Client|AsyncClient)` is either migrated or listed; C-56's migration list must include them.
- F-C462-3 LOW, test gaps (survivors, reasoning 5): pin each of `AsyncClient`, `put`, `patch`, `delete`, `head`, `options`, `request` as flagged; pin `build_opener(ProxyHandler())` and `ProxyHandler({'a': 'b'})` as flagged; pin `from httpx import Client as C` as flagged.
- F-C462-4 LOW: add `urllib.request.urlretrieve` to the urllib rule; decide on the Anthropic SDK and `requests` in C-56 (today 1 and 0 sites).
- F-C462-5 LOW, for C-56: check what `trust_env=False` turns off besides the proxy (reasoning 8) before the mass change.

CONCLUSION: PASS WITH CONDITIONS on b47ee05cd97947aebd738cd26c2406bcf1de9ca3. The lint does what its text says on the shapes it names, the allowlist equals the scan exactly (63 sites, 58 keys), the whole tools suite and CI 7 of 7 are green; it does not see two auth-carrying clients in lifecycle-manager and its own blindness guard will fail when the work it supports is done. Coordinator still needs GX10 16/0 on the exact head (the PR says unverified there).

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13 only; 3.11, 3.12 and 3.14 only through CI.
- Did not test `trust_env=False` against a real proxy or certificate setup (reasoning 8 is from general knowledge).
- Did not read the builder note for the PR's own 10 mutants and so did not compare them with mine.
- Did not examine shell or node HTTP clients, and not the 7 skipped tests.
