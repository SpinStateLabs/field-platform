# C-194 reviewer report: services/delegation-authority mint, revoke, list-bound reach, introspection, expiry (main 7b4d6f7 code; delegation code unchanged to b1872ee)

VERDICT: no path mints or revokes without its checks when the DOA roster is armed; 87 mutants run, 71 killed, 16 survived, none a bypass. Two design facts matter for a reader: with `FIELD_DOA_ROSTER` unset the grantor, scope and TTL checks do not run, and there is no renew route (renewal is a tool that mints and revokes).

OBJECTIONS FIRST
1. R-10 covered the alias-mint path; this round mutates the rest of api.py (v1 43 mutants, v2 40 sampled of 102) and store.py (5); `cli.py` and `doa.py` were not mutated.
2. I read `mint` (api.py:150-330), the revoke handler (:337-385) and parts of introspect; not every line.
3. The clones used for mutation were at 7b4d6f7; delegation-authority source is identical to b1872ee (the later PRs touch other files).

ASSUMPTIONS
1. delegation-authority suite 162 tests (10 s); kill set `tests` from the service directory. [HIGH]

REASONING
1. Mint checks (read): `check_granted_by` (returns bool since PR 55), registry `require_active_agent` (404, 409 retired or killed, 502), then if `FIELD_DOA_ROSTER` is set: roster load failure -> 503, grantor on the roster and active (`D.grantor` 403), `may_delegate(scope)`, manifest resolvable (`D.scope` 422), scope inside `manifest.delegation.scope`, manifest `delegation.expiry` parseable and not past (`MANIFEST_EXPIRED` 422), token lifetime within `max_ttl_days` (403), token expiry not after the manifest expiry; then the list-bound reach check for non-alias mints; then the token, the ledger event (fail closed: 502 "ledger unreachable - refusing to mint"). Mutants on these branches: 39 of 43 killed in v1. [HIGH]
2. INFO, F-C194-1 (design, known): with `FIELD_DOA_ROSTER` unset the roster block is skipped (`doa_checked: false` in the ledger row): no grantor, scope-in-manifest or TTL-cap check runs on mint. The topology lint requires the roster to be armed on deployed estates and lists the exceptions (C-143); the code path is intentional. [HIGH]
3. INFO, F-C194-2 (design): there is no "renew" in delegation-authority; renewal is `tools/renew_token.py` minting a new token and revoking the old (C-195). Revoke (api.py:337-385) is guarded by `guard_revoke` (operator scope `revoke`); only a list-bound identity (the machine verifier) is further bounded by the agent's manifest; an ordinary identity holding `revoke` can revoke any token, by scope design. [HIGH]
4. LOW, F-C194-3: expiry boundaries: api.py:186 `expires <= now` -> `<` and :257 `manifest_expiry <= now` -> `<` both survive: a token expiring exactly now and a manifest expiring exactly now are not pinned. [HIGH]
5. LOW, F-C194-4: ledger payload fields unpinned: api.py:313 (`"expires_at"` key of the `delegation.mint` event payload emptied) and :382 (`"revocation_id"` of `delegation.revoke`) survive: the evidence rows' field names are not tested. [HIGH]
6. LOW, F-C194-5: `raise HTTPException(502, "registry unreachable - refusing to mint")` deleted (L165) survives: with the registry unreachable the handler would fail with a NameError (500) instead of the designed 502; still no mint, but the designed status is untested. L284 `if not via_alias` -> True and L356 `list_bound_applies` -> True survive (the extra list-bound call is a no-op for ordinary identities: near-equivalent). [HIGH]
7. LOW, F-C194-6: other survivors: request-model constants (L79, L80, L82 minimum lengths and `gt=0`), L86 validator name, `data_path` defaults (L107-108), the form parser of the OAuth introspect route (L435), store.py:114 (`stored == token.max_spend_usd` in the save path). [HIGH]
8. Pinned: introspection active/expired/revoked/other-agent outcomes, revoke 404/403/409 and ledger fail-closed, the unknown-token 403 for list-bound (PR 77), mint 409 for retired or killed agents, D.grantor and D.scope clauses, MANIFEST_EXPIRED clauses (R-10, C-114 and this round). [HIGH on mutants]

CONCLUSION
No mint, revoke or introspection path without its checks was found; the two INFO items are by design. Add tests for the two exact-now boundaries, the mint-registry-502, and the event payload field names. Not done: cli.py, doa.py, a probe of the OAuth introspect form route.
