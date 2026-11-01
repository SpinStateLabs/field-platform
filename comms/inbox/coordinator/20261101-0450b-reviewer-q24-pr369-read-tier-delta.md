VERDICT PASS WITH CONDITIONS on 40951fe60f0f3916256d0f6e9c55f2759bd5666b (PR 369, Q-24, Lane 15 reviewer; HIGH CARE: a read key must never authorise a write; delta 6f1fd7d0..40951fe6 plus an independent probe of the whole guard; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. The guard judges a request by path strings while the router dispatches by its own regexes; every spelling gap is a read key reaching a write route. A matcher can only be shown unsound by a corpus, never shown sound.
2. The builder note (C-1066) says the mutant "request URL path only" survives as equivalent because the URL path alone covers the control-character spellings. That is wrong for templated entries (proven below); the equivalence claim is the kind of reasoning that lets a gap in.
3. A read key authorises any safe-method request not on the write-only list: an adopter's state-changing GET that is not listed is open to the read key. By design and documented (authn.py docstring), but it is the whole attack surface of this PR.
4. No service installs the tiers yet (grep of services and package sources: no caller passes `service=` or `write_only_paths=`), so nothing here is exposed in production today; the verdict is for the library.
ASSUMPTIONS: head current (git ls-remote = full sha above); delta = one test commit, +39 lines in packages/field-core/tests/test_authn_tiers_c772.py (git diff 6f1fd7d0..head --stat); Starlette 1.7.0, FastAPI 0.162.0 as installed here; made-up keys only.

REASONING
1. Baselines: test_authn_tiers_c772.py 37 passed; whole field-core suite 1169 passed, 1 skipped (HIGH, run).
2. Differential probe (own code, real FastAPI app with write-only entries: an exact path, a plain template, a middle `{p:path}`, a trailing `{p:path}`, and the two internal operator routes; run with root_path "" and "/api"): 18 base paths x about 30 spellings (case, trailing and double slash, encoded and doubled slashes, dot segments, ";", "?", "#", NUL, space, tab, CR, LF, CRLF, backslash, non-ASCII, encoded letter) x 7 methods = 6692 requests with the read key. Result: 0 violations: no write method (POST, PUT, DELETE, PATCH) answered other than 401/404/405/422, and no write-only GET route answered 200 (34 legitimate read 200s) (HIGH for this corpus, MEDIUM beyond it).
3. Probe sensitivity: the same probe against two mutants of the matcher: scope-path-only gives 18 violations, URL-path-only gives 8 violations, all 8 on the templated route `/rotate/{rid}` with a trailing %0A, %0D, %09 or %0D%0A (both root paths). Cause (probe): for `/rotate/%0A` the URL path is `/rotate/` (the control character is dropped) while the scope path is `/rotate/\n`; the first does not match the template, the second does, and the router dispatches on the second (HIGH, run).
4. PR tests against 20 mutants of authn.py: 17 killed, 3 survived. Survivors: (a) URL-path-only (objection 2: NOT equivalent, finding F-Q24-1); (b) `startswith(root + "/")` loosened to `startswith(root)`: only adds spellings that cannot match an entry (equivalent in effect, fail closed); (c) runtime equal-key guard removed: equivalent (an equal key is accepted as the full key either way); (d) `.upper()` removed from the method test: stricter (a lowercase method is then refused), no power gain. Killed include: all four method-set mutants (POST, DELETE added, read key on any method), write-only check removed, internal paths emptied or reduced, scope-path-only, both path-converter variants, empty-capture prefix dropped, root-path spelling dropped, install equal-key check dropped, no-secret read-key mode, trailing-slash normalisation, service-key precedence (HIGH, run). File restored (diff clean).
5. The C-1057 conditions: F-C1057-369-1 (trailing control characters on a write-only path) pinned by the new tests for the EXACT-entry case only; F-C1057-369-2 (middle `{p:path}` empty capture) pinned, mutant `.+` killed (HIGH).
6. merge-tree: clean against main and with PRs 325, 348, 352, 355, 356, 375, 381, 394.

FINDINGS
- F-Q24-1 MEDIUM-LOW (HIGH care): no test pins a TEMPLATED write-only entry with a trailing control character; the correct result depends on the scope-path spelling, and deleting that spelling lets a read key reach a templated write-only GET (probe, 4 spellings). Fix: add a case `GET /rotate/%0A` (template `/rotate/{rid}`) to the new control-character test. The builder's "equivalent" note should be corrected.
- F-Q24-2 LOW: lowercase method is untested (survivor d); stricter than needed, no risk.
- F-Q24-3 INFO: tiers are not installed by any service yet; deployment wiring (and its write-only lists) needs its own review before a read key exists on an estate.
- Carried: objection 3, the unlisted state-changing GET (design).

NOT VERIFIED: CI, GX10, behaviour behind a real reverse proxy that rewrites paths, other ASGI servers than the test client (uvicorn spelling of control characters in a raw request line was not exercised).

CONCLUSION: PASS WITH CONDITIONS. No read-key-to-write path found in 6692 probed requests, and 17 of 20 mutants are killed; one condition: pin the templated trailing-control-character case (F-Q24-1) before a read key is issued anywhere.
