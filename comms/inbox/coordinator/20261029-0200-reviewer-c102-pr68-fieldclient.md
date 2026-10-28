# C-102 reviewer report: PR 68 fix/fieldclient-no-env-proxy @23a1b81 (C-53)

VERDICT: PASS on 23a1b81 for the two security findings (C-41 findings 1 and 2). Two LOW test gaps; neither blocks merge.

OBJECTIONS FIRST
1. The refusal line `raw = b""` may be dead weight: a truncated JSON body already fails to parse.
2. The "at the cap" test may not test the cap.
3. `NO_REDIRECT` is an import-time global; other opener paths could still carry the proxy.

ASSUMPTIONS
1. Head exactly 23a1b81 (bundle on GX10 `~/ff-work/wt-fieldrev-68`, `git rev-parse HEAD` printed 23a1b81a4d5...). [HIGH]
2. Base main a8bd47c. [HIGH]

REASONING
1. Suites on GX10: packages/field-agent 118 passed; packages/field-core 950 passed. [HIGH]
2. New test file vs main's source: proxy test FAILS on main (real regression test, proven), the three MAX_RESPONSE_BYTES tests fail on main by AttributeError. [HIGH]
3. Hand mutants (full field-agent suite):
   - M2 drop `ProxyHandler({})`: KILLED. M4 `read(MAX)`: KILLED. M5 unbounded `read()`: KILLED.
   - M1 `len(raw) > MAX` -> `>=`: SURVIVED. `test_a_reply_at_the_cap_is_still_read` computes `pad` but sends the unpadded 21-byte reply; it never sends exactly MAX bytes. [HIGH]
   - M3 delete `raw = b""`: SURVIVED. A valid JSON verdict followed by whitespace padding beyond the cap would then be parsed from the first MAX+1 bytes. Probe with the refusal in place: ALLOW + padding => BLOCK (HIGH). The refusal is live code but no test pins it, because the oversize test pads inside the JSON, so truncation fails the parse regardless. [HIGH]
4. `test_the_default_opener_registers_no_proxy_handler_...` builds its own opener and asserts `handlers is not None` (tautology); the subprocess test is the real one and kills M2. LOW. [HIGH]
5. Callers: only `field_client.py:160` uses `NO_REDIRECT`/`.read(` on this opener; `canary.py:357,359` use their own `resp.read()` on a different path (not this client). `git grep` for field_client/NO_REDIRECT outside field-agent: CHANGELOG.md, docs/runbooks/token-renewal.md, plugins/.../rest-api.md (docs only). No other package depends on `read()` without an argument. [HIGH]
6. The `_Resp.read(amt)` test-double change matches `http.client.HTTPResponse.read(amt)` semantics. [MEDIUM]
7. README wording accurate to the code. Note: `canary.py` has its own unbounded `resp.read()` (:357) and `exc.read()` (:359); not in C-53 scope, recorded as F-C102-3 (LOW). [MEDIUM]

CONCLUSION
PASS at 23a1b81. Optional hardening: make the cap test send exactly MAX bytes (and MAX+1), and add a valid-JSON-plus-padding case so `raw = b""` is pinned. F-C41-1 and F-C41-2 become "fixed at 23a1b81, pending merge". Cost-optimizer note in `inbox/coordinator/20261029-0200-reviewer-c102-note-for-cost-optimizer-coordinator.md`.
