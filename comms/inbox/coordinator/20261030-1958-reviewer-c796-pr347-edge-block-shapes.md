VERDICT: PASS WITH CONDITIONS on 10dfdeffa4d9a8d8a164aadee9ee1c744a7d7434  (UNVERIFIED: cloud reviewer, no GX10, no real Caddy, CI not read)

C-796, PR 347 (tests: the edge-block checker sends the 15 extra C-27 probe shapes; C-32). Head moved from 3c2d51c to 10dfdef (C-671). Two files change: integration/demo/fixtures/kr-edge/check_edge_block.py (+37 -5) and tools/tests/test_kr_edge_block_r2.py (+62 -?). This SHA only.

OBJECTIONS FIRST
1. The summary line overstates what the edge refused. check_edge_block.py (check(), the final print): `n` counts the six informational shapes per route, and only gating failures enter `problems`, so the line says "<n - len(problems)> refused at the edge". Probe: a local stand-in answering every informational path with 200 (80 info lines printed) and every other path with the edge's 403: the checker reported 2 problems (both from the console-root overlap, objection 3) and the summary "432 requests ... 430 refused at the edge". 78 requests that got through were counted as refused. Exit code is right; the log line is wrong. Confidence HIGH (observed).
2. The six informational shapes (ahead of the prefix, double encoding, lower-case %2f, backslash, trailing dot) are not asserted by the check: a regression where the edge passes them through leaves CI green with an `info:` line in the log nobody is forced to read. The docstring and commit say so openly ("not yet proven against a real proxy"; promote to gating when the log shows 403 on every image). So the card's "each asserted" is true for 20 shapes and false by design for 6. No promotion date or owner. Confidence HIGH.
3. Distinctness: for every prefix and route the 20 gating shapes are distinct (20 of 20; 320 distinct across 8 prefixes x 2 routes). The six informational shapes are distinct per prefix, but for the console root (empty prefix) two of the six equal two gating shapes ("//operator/..." and "/./operator/..."): so for that prefix only four are new. The test file notes the repeat. The card counts "15 extra shapes": the list in `_variants` adds 15 beyond the original five (5 + 15 = 20), confirmed. LOW.
4. Real-proxy behaviour was not exercised by this review or by the PR. Python's own http.server rewrites a leading "//" to "/", so my local stand-in saw 16 of the leading-slash info shapes without the doubled slash; that is my harness, not the checker (urllib sends the path as given). Whether urllib, the proxy or a CDN normalises other shapes (dot segments, %2e%2e, backslash) before the edge sees them: not verified; all 20 gating shapes arrived verbatim at the stand-in (396 of the 416 intended paths, the 16 above are the only mismatches, plus the spoof duplicates). Confidence MEDIUM.
5. Credentials and addresses: none in the probes. The request body is a fixed placeholder (operator id of a service, 64 zeros as the key hash); the perimeter secret is read from FIELD_SHARED_SECRET and sent as a header on every request to whatever base URL is passed, including http:// (probe: header present on all 432 requests); it is never printed or put in argv. The tests use an `edge.invalid` base and a fake secret string. No estate address, flag value or deploy status in the diff. A caller passing a non-internal http base would send the secret in cleartext; pre-existing, not new here. Confidence HIGH.
6. Status check mutant survives: removing `status != 403 or` from the gating test leaves the suite green (36 passed), so a 200 carrying the edge's own body text would pass; nothing pins that a non-403 with the right body fails. LOW.

ASSUMPTIONS
A1 Card scope: what changed, 15 shapes distinct and asserted, no real credential or estate address. A2 The shapes are those named in the C-27 report. A3 No real proxy here.

REASONING / CHECKS
- Tests: tools/tests/test_kr_edge_block_r2.py 36 passed (with the field-core sources on the path; without them 15 pass and one fixture errors on import, an environment fact).
- Probe against a local stand-in server that records raw paths and always answers with the edge's 403: 0 problems, 432 requests (8 prefixes x 2 routes x (20 gating + 1 spoofed XFF on the plain path + 6 info)); the intended-versus-received comparison above.
- Mutants on the checker (each restored, nothing committed): 20 single-line mutants: dropped each of the 15 new gating shapes individually or in pairs (doubled slash, encoded o, dot segments, NUL, title case, encoded hyphen, semicolon parameter, trailing slash, upper case) KILLED; info shapes made non-sent KILLED; info line removed KILLED; info made gating KILLED; body check removed KILLED; spoofed XFF removed KILLED; each of four info shapes neutralised KILLED; status check removed SURVIVED (objection 6). 19 of 20 killed.
- The expected-shape test uses literal strings for one prefix (LEDGER_VERIFY_HASH and its info list), so the expectation is not a copy of the implementation (C-671 asked for this): CLOSED.
- Commits: 2, author and committer Don Hagell no-reply.

CONDITIONS
C1 (non-blocking) Count only gating requests in the "refused at the edge" line, or print the info count separately.
C2 (non-blocking) Name an owner and a trigger for promoting the six info shapes to gating (a real-Caddy run).
C3 (non-blocking) Pin that a non-403 with the edge body fails.
C4 (non-blocking) Make the info shape set disjoint from the gating set for the console root, or say so in the docstring.

NOT VERIFIED
GX10, CI by run id, any real Caddy or other proxy answer, behaviour of urllib for control characters in other shapes, the other edge files (Caddyfiles).

CONCLUSION
The 20 gating shapes are distinct, each asserted by a 403 plus body, and their tests bite (19 of 20 mutants die). The six extra shapes are reported, not asserted, and the summary line miscounts them as refused. No credential or estate address is sent. PASS WITH CONDITIONS, UNVERIFIED.

CORRECTION (same session): objection 4 gave "396 of the 416 intended paths" arrived verbatim; that figure is wrong. The probe showed 16 intended (method, shape) pairs not received verbatim, all of them the leading-"//" informational shape (an artifact of the stand-in server); every other intended pair was received as sent. I did not compute a 396 count.
