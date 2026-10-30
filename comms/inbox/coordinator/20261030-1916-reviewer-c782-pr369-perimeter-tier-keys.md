VERDICT: FAIL on f685e08 (the carded head, as built); PASS WITH CONDITIONS on 1f4fbc7e527bcfdd42d32adf89371b4ba186948d (the PR head now)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-782, PR 369 (field-core per-tier perimeter keys, C-772). The card names f685e08; the PR head has since moved to 1f4fbc7 (two commits after f685e08, 8b5d459 and 1f4fbc7, answering the C-783 review). Each verdict applies to its own SHA only.

OBJECTIONS FIRST
1. At f685e08 a read key passes a write-only GET in two spellings. write_only_paths was matched exactly against request.url.path (authn.py at f685e08, the `request.url.path not in write_only` test). Probe (FastAPI TestClient, one app, read key set, full key set): a write-only entry given as a template (`/mut/{x}`) was not matched, GET /mut/1 with the read key returned 200; with root_path set, GET <root>/<write-only path> with the read key returned 200. Both returned 401 at 1f4fbc7. This is the fail-closed gap the card asked about. Confidence HIGH (observed at both heads).
2. No service adopts the tiers. Every service's api.py calls install_authn(app, ...) with no service= and no write_only_paths (grep of services/*/src). If FIELD_READ_KEY is set in a deployment, the generic read key then reaches every GET of every service, including any GET that changes state, because nothing lists them. Whether such a GET exists I did not enumerate. Confidence HIGH on non-adoption; MEDIUM that this matters. Condition C1.
3. A read key never authorises a POST, so the Tier 1 POST-but-read-only routes (crosswalk /crosswalk, /crosswalk/markdown, /pack; replay /replay, /replay/markdown; delegation /introspect, /oauth/introspect: seven, per the field-mcp catalog in PR 368) answer 401 to a read-key caller (probe: POST with the read key returned 401). A field-mcp process given only a read key will fail on those 7 of its 49 tools. Not a security fault; a design gap to settle. Confidence HIGH. Condition C2.
4. Mutants that survive: M3 (compare_digest replaced by ==) survives; a timing property is not testable by assertion, so constant-time rests on code reading (_same uses hmac.compare_digest on both keys, authn.py). M6 (drop the later-env-change guard) survives; I judge it equivalent, since a presented value equal to the full key passes the full-key branch either way. Confidence MEDIUM on equivalence.
5. HEAD and OPTIONS are accepted as safe methods with a read key. On a route that also handles OPTIONS with a side effect this would pass; none observed. Confidence LOW.

ASSUMPTIONS
A1 Card scope: can a read key pass a write route; comparison constant time; keys absent from results, errors, logs; compatibility with single-key services. A2 The services I grepped are all that adopt field_core.authn. A3 FastAPI/Starlette in my sandbox behaves as in CI.

REASONING / CHECKS
- Tests at 1f4fbc7: tests/test_authn*.py 28 passed. Mutants on authn.py at 1f4fbc7: M1 safe methods plus POST KILLED; M2 ignore write_only KILLED; M4 allow equal keys at install KILLED; M5 read-key-only no longer enforced KILLED; M7 per-service read key ignored KILLED; M3 and M6 survived (objection 4). Restored; worktrees removed, nothing committed.
- Behaviour at 1f4fbc7: read key GET on a normal route 200; read key POST 401; read key on a write-only GET 401 for the plain, template and root_path spellings; no key or a wrong key 401; empty header 401; /health open without a key; read key set with no full key: GET with read key 200, POST with read key 401, GET without a key 401; equal keys refused at install with TierKeyError; the 401 body carries fixed text only and contains neither key. Trailing-slash spelling: the middleware passes the read key but the redirect target is then refused 401 (the client resends the header); a route registered WITH a trailing slash is covered by the 1f4fbc7 normalisation.
- Single-key compatibility: with no read key set, behaviour is the earlier path (full key required, secret unset leaves open demo mode). With a read key set and no full key it fails closed for non-safe methods, as the docstring says; a GET with the read key is allowed in that state. Migration note for Don: setting only FIELD_READ_KEY on a deployment that had no secret changes it from open to GET-with-key-only. HIGH on behaviour.
- Key handling: tier_key_problem returns fixed text; read_auth_headers never returns the full key; I found no log line or error that carries a key in the three changed files. HIGH for these files only.
- Commits: all 4 commits author and committer Don Hagell no-reply. Diff scan (3 files, +456 -3): no address, token or key-shaped literal other than short test placeholders.

CONDITIONS
C0 (blocking at f685e08) Merge only at or after 1f4fbc7; at f685e08 objection 1 is a real read-key write bypass.
C1 (blocking before any deployment sets a read key) Services must pass service= and write_only_paths, and the GET routes that change state must be enumerated; today nothing adopts it.
C2 (non-blocking) Decide how the seven read POST tools authenticate under a read key.
C3 (non-blocking) Add a test or note that constant-time rests on _same.

NOT VERIFIED
GX10 full 16-suite run, CI by run id, behaviour of any real service under a read key, whether any live GET changes state, logs of a running service.

CONCLUSION
f685e08 fails the card's first question (a read key could pass a write-only GET). 1f4fbc7 closes it; PASS WITH CONDITIONS C0-C3, UNVERIFIED. Both findings were also in the C-783 scope.
