VERDICT: PASS WITH CONDITIONS on 39303a99c226616f06644108d410fce5011269aa (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's test file ran: 83 passed)

Head matches the card. Three commits on main (f9c0adb the module, 7688aa4 the ENVIRONMENT.md row, 39303a9 the C-746 fixes); author and committer are the no-reply Don Hagell identity. Files: packages/field-core/src/field_core/http.py (+96, new), tests/test_http_client_c487.py (+256), docs/ENVIRONMENT.md (+1). Slice 1 of C-487: the constructor only; no call site is migrated here.

OBJECTIONS FIRST
1. Can a caller override trust_env or follow_redirects through **kw? NO. PROVEN: passing either, or proxy, proxies, mounts, transport, event_hooks or cert, raises ValueError ("... is fixed by field_core.http"); the async constructor does the same; the two literals are on the call itself so the C-57 lint reads them. An upper-case spelling is not a keyword and fails inside httpx. HIGH.
2. "Timeout required and never wait-forever" is closed for None, 0, negative, NaN, infinity, a bool, a string, and an httpx.Timeout with any None or non-positive part. NOT closed for a huge finite number: timeout=1e308 and timeout=10**9 are accepted and are wait-forever in practice (the check is "positive and finite"). Also accepted: 1e-9. LOW-MEDIUM.
3. verify: only True or an ssl.SSLContext; False and a path string are refused. But a context the caller builds is trusted as given: an unverified context (certificate checking off, built with the standard library's private helper) was ACCEPTED, as was a context subclass. The docstring says the caller builds the context; nothing stops a context that checks nothing. A secret-bearing client could therefore be built with verification off through this door. MEDIUM-LOW (by design, but "verify=False is refused" reads stronger than what is enforced).
4. base_url is not validated: a URL with credentials in it (userinfo) and a link-local address were both accepted. The design note for the MCP client (C-773/C-488) wants the internal-host predicate on the base; that predicate (PR 356) is not used here, so every caller must apply it itself or the constructor must grow it. The module is silent about it. MEDIUM-LOW for slice 1; the MCP client card must not assume the constructor checks the host.
5. FIELD_EGRESS_PROXY: blank means none; http and https URLs with a host are accepted (also in upper case); an ftp URL, a bare host:port, "http://" and an unterminated IPv6 bracket are refused; the refusal text never includes the value (probed with a credentialed URL). With it set the client mounts exactly one proxy; an ambient HTTP_PROXY is ignored (client built with the variable set: no mounts, trust_env False). The proxy is by design a place the secret headers go; a plain-http proxy URL sends them in clear to the proxy. LOW (documented as the one explicit proxy).
6. Unmigrated call sites: none migrated in this PR; the C-57 allowlist still holds 58 entries, unchanged. The lint (test_http_env_proxy_lint_c57.py) does not follow field_core.http.client (it is not httpx), so a migrated site disappears from the allowlist scan, which is the intent; nothing yet forces a new client through this module (a new bare httpx.Client is still a finding). HIGH.
7. Overlap with PR 356 (is_internal_host) and the MCP client card C-773: no shared code; the constructor does not call the predicate (objection 4). Merge order is free by files.
8. No response-size cap here (stated): each caller bounds its own reads (FieldClient and the canary do; the heartbeat client did not until PR 359). LOW.

ASSUMPTIONS
A1 "Override" = any way for a caller to end up with a client that reads the proxy environment, follows redirects, has no timeout, or skips certificate checks. A2 Probes call field_core.http.client and async_client directly with httpx 0.28.1; ssl contexts built with the standard library; no network traffic.

REASONING
1. Probe table: as in objections 1-5 (about 45 argument combinations). HIGH.
2. Mutants (each alone, restored, worktree removed, nothing committed): trust_env True in the sync constructor -> 3 failed; follow_redirects True -> 2; the same two in the async constructor -> 2 and 2; each of trust_env, transport, proxy and event_hooks removed from the pinned list -> 2 each; verify check off -> 8; timeout None accepted -> 2; timeout-part check off -> 14; the finite check off -> 2; bool accepted -> 2; the proxy value echoed in the refusal -> 10; proxy scheme check off -> 6; proxy host check off -> 2; the explicit proxy ignored -> 1. 17 of 17 red. HIGH.
3. Diff scan: no address, SHA, flag value, deploy status or credential; the proxy examples are placeholders. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The pinned settings cannot be overridden, the checks have red tests under 17 of 17 mutants, and the proxy refusal leaks nothing. Gaps: a huge timeout, a caller-built context that checks nothing, and no base-URL validation. Conditions, none blocking slice 1:
- C1 F-C778-1: add an upper bound on timeouts (for example 600 seconds) or state that large values are the caller's choice.
- C2 F-C778-2: refuse an SSLContext whose verify_mode is not CERT_REQUIRED or whose check_hostname is off, or document that a context is trusted.
- C3 F-C778-3: validate base_url (no userinfo; the internal-host predicate where the policy applies) here or in a named wrapper, before the MCP client uses this constructor.
- C4: list in the next slice which call sites migrate, so the allowlist shrinks.

FINDINGS
F-C778-1 LOW-MEDIUM, packages/field-core/src/field_core/http.py (_positive/_checked: no upper bound on timeout). PROVEN.
F-C778-2 MEDIUM-LOW, same file (_checked: verify accepts any SSLContext, including one that does not verify). PROVEN.
F-C778-3 MEDIUM-LOW, same file (client/async_client: base_url unchecked, userinfo and link-local accepted). PROVEN.
F-C778-4 LOW, same file (_egress_proxy: an http proxy URL carries secret headers in clear; explicit by design). HIGH.
F-C778-5 INFO, tools/tests/http_env_proxy_allowlist.txt (58 sites, none migrated yet). HIGH.

NOT VERIFIED: behaviour on other httpx versions; real traffic through the proxy; CI; the rest of the field-core suite.
