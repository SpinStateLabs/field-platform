# Lane O reviewer: PR 490 (S-A1, field-core authn non-ASCII x-field-auth) @ddf8b63993296f4982a5d2f64c3e04fa02d73890. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head ddf8b639. Lane A (field-core). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH). I did not write the head.

Objections first: (1) wire-encoding assumption: the fix encodes the Starlette-decoded str back with latin-1 and the secret with UTF-8. This is right only while the ASGI stack decodes header bytes as latin-1 (true for Starlette, general knowledge, MEDIUM); the builder says the test client normalises header bytes, so latin-1 vs UTF-8 on the real wire is not tested end to end. (2) `errors="replace"` would map any char above U+00FF to "?", so a presented value with such a char could equal a secret containing "?"; not reachable through Starlette (latin-1 decode cannot produce one), MEDIUM; "strict" would be safer or equally fine. (3) the same pattern in a second place is encoded differently: services/force-gateway/src/force_gateway/api.py:260 passthrough_honoured does `presented_auth.encode("utf-8")`. For a NON-ASCII wire value the middleware (latin-1, this PR) and passthrough_honoured (UTF-8) now disagree, so a non-ASCII configured secret passes the middleware but the passthrough exemption is refused; ASCII secrets (the normal case) are unaffected (read, not run, HIGH for the code, MEDIUM for impact).

Run here (cloud, packages/field-core, relative PYTHONPATH): tests/test_authn.py 9 passed; whole packages/field-core/tests 1549 passed, 2 skipped, matching the builder. NOT run: the 16-suite set; force-gateway suite; CI.

Mutants on authn.py (17, scratch worktree on the exact head; each against test_authn.py, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 non-ASCII header value is 401, not a 500 (revert to str, ascii-ignore bypass, ascii strict, never refuse, status 500) | 5 | 5 | 0 |
| B2 right key passes, wrong key 401 (inverted, truncated compare, always 401, prefix match) | 4 | 4 | 0 |
| B3 non-ASCII configured secret authenticates (secret ascii, latin-1, presented utf-8, ascii-ignore) | 4 | 4 | 0 |
| B4 401 body names x-field-auth (text, empty, key, missing-header default) | 4 | 4 | 0 |
| Total (counted from the rows) | 17 | 17 | 0 |
No survivor. 17 of 17 is a small-surface result, not proof of the wire behaviour in objection 1.

Findings:
- F-O490-1 MEDIUM-LOW: force-gateway passthrough_honoured encodes UTF-8, authn.py now latin-1 (objection 3); pin with a test or align the two via one shared helper in field_core.authn.
- F-O490-2 LOW: `"replace"` to `"strict"` (objection 2).
- F-O490-3 LOW: add an end-to-end check with a real ASGI server (raw UTF-8 bytes) for objection 1.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 F-O490-1 named (fix in this PR, or a recorded follow-up card) because it is the same secret check on the same header.
Optional, NEW PR only after the head is frozen: F-O490-2/3.

Tokens/cost line: not available to me. I do not know.
