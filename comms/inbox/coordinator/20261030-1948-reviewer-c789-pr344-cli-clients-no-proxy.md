VERDICT: PASS WITH CONDITIONS on 627532e800633936fb17bf25b530671e46042572  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-789, PR 344 (lifecycle-manager: the CLI's estate clients never read the proxy environment or follow a redirect), after C-732 (PASS WITH CONDITIONS on fd377ed). Head moved one commit (627532e). This SHA only. The card's question "any client still reading trust_env": yes, the served path; see objection 1.

OBJECTIONS FIRST
1. Four clients on the `serve` path still read the proxy environment. Probe (HTTP proxy variable set, then each constructor inspected): api.delegation_client(), api.killswitch_client(), field_core LedgerClient() and RegistryClient() (own-client mode) all report trust_env True; follow_redirects is False on all of them (httpx default). cli._service_client reports trust_env False, follow_redirects False. Callers: api.py:148-150 and :409-411 (RegistryClient()/LedgerClient()), cli.py:469 (serve builds LedgerClient()), api.py:114-135. The kill-switch client is the one that carries the operator pair on the auto-kill path, so an ambient proxy would see that request. This is the deferred F-C639-2 / C-732 P2, stated in the allowlist note and the commit text; it is not closed here and the PR does not claim to. Confidence HIGH (observed).
2. The proxy lint cannot see two of the four. PerRequestAuthClient (api.py:87) subclasses httpx.Client and the two builders instantiate it by that name; tools/tests/http_env_proxy_allowlist.txt has no entry for api.py, and the lint (test_http_env_proxy_lint_c57.py, 21 passed) is green with them. So "the allowlist equals the scan" holds while two leaking clients are outside the scan. The note added to the allowlist names only the two field-core entries as what lets `serve` read the proxy environment; the real count is four (C-732's own count). Confidence HIGH on the probe, MEDIUM on how the lint matches names (I did not read its AST rules line by line).
3. P2 (merge order of PR 318 and 330, which conflict) is a coordinator decision and is open. Not a defect of this PR.
4. The CLI client's redirect and proxy behaviour is pinned (below), but nothing pins `serve`; whoever fixes serve needs a test that goes red when a client there reads the environment. Confidence HIGH.

ASSUMPTIONS
A1 Card scope: each C-732 condition and whether the head closes it; any client still reading trust_env. A2 httpx semantics: `Client(trust_env=True)` is the default and reads the proxy variables. A3 The CLI verbs are the scope of the PR title.

REASONING / CHECKS
- C-732 conditions: P1 (per-verb wiring test with a stand-in engine; behavioural proxy and redirect counts per builder entry; per-service ownership of each wrapper; the api.py "ONLY place" docstring): CLOSED. The docstring now says the CLI builds its own (api.py:124-126). The 627532e test file (397 lines) covers the verbs (sweep, provision, decommission), proxy listener and redirect counts, perimeter secret on every request, pair only on guarded routes, per-service ownership and timeout. P2: open (coordinator).
- Tests: lifecycle-manager 265 passed; tools proxy lint 21 passed.
- Mutants on cli.py, each against the PR's test file (restored, nothing committed): trust_env False→True KILLED; follow_redirects→True KILLED; registry wrapper built without the injected client KILLED; ledger wrapper likewise KILLED; timeout not passed through KILLED; perimeter header dropped KILLED; guarded routes list emptied KILLED; delegation wrapper built from the wrong service KILLED. Eight of eight.
- Allowlist edit: one line removed (cli.py::_service_client) and the note added; the removal is correct because the site now sets trust_env False. 
- Commits: 3, author and committer Don Hagell no-reply. Diff scan: no address, flag value, credential or deploy status. src change is 8 lines (cli.py, api.py docstring).

CONDITIONS
C1 (non-blocking for this PR; blocking for any claim that lifecycle-manager is closed) Close the four serve clients (trust_env False) via PR 318/330 or C-487, and add a serve-level test that goes red on a mutant.
C2 (non-blocking) Make the lint see subclasses of httpx.Client (or give PerRequestAuthClient a pinned trust_env=False and a test), and correct the allowlist note to four clients.
C3 (coordinator) Order PR 318 and 330.

NOT VERIFIED
GX10 full set, CI by run id, behaviour against a real proxy beyond the PR's local listener tests, PR 318/330 content, the lint's matching rules in detail.

CONCLUSION
The CLI estate clients are closed and well pinned: 8 of 8 mutants die. The served path is not: four clients still read the proxy environment, two of them invisible to the lint. Mergeable for what it claims. PASS WITH CONDITIONS, UNVERIFIED.
