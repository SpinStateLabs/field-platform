VERDICT: PASS WITH CONDITIONS on 3c2d51c29f20146f4958d5dcff9875642e5ae094 (UNVERIFIED: cloud reviewer, no real proxy, CI not read)

Same PR and head as my report 20261104-0455-reviewer-c650-pr347-edge-probe-shapes.md (head re-checked: still 3c2d51c). This card asks: are the 15 shapes distinct and each asserted; any probe that sends a real credential or estate address. The full table and mutants are in the C-650 report.

OBJECTIONS FIRST
1. Real proxy behaviour is not proven: the checker sends 20 variants per route (5 old, 15 new) and expects the edge's own refusal for each; whether the real edge refuses every shape is only established by a green edge-smoke job on this head, which I did not read. MEDIUM.
2. The test rebuilds the expected list with the same string operations as the checker, so a shape wrong in both passes both (the arithmetic pin 8 x 2 x 21 and the set equality catch a missing or altered shape, not a wrongly conceived one). LOW.
3. Not covered: shapes ahead of the service prefix, double and lower-case percent-encoded slashes, backslash, trailing dot (F-C650-1, unchanged).

REASONING
1. Distinct: for every prefix (8) and route (2) the variant list has 20 entries, all distinct and none equal to the base path (computed). HIGH.
2. Each asserted: the test's want-set of (url, method, spoof) equals the calls made, count 8 x 2 x 21 = 336; mutants removing, altering or re-spelling a shape turn it red (four mutants run under C-650, all red). HIGH.
3. Credential or estate address: the perimeter secret is read from the environment, sent only as a header, never printed; the spoofed forwarded-for value is the loopback literal; the diff adds no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS, as C-650: read the edge-smoke run on this head by id before treating the edge as covered; widen the shape list or state the limits; update the stale docstring (check_edge_block.py:3-14).

FINDINGS
F-C766-1 MEDIUM, integration/demo/fixtures/kr-edge/check_edge_block.py:40-54 (real-edge refusal of all 15 shapes unproven here). HIGH.
F-C766-2 LOW-MEDIUM, same file (shape classes not covered). MEDIUM.
F-C766-3 LOW, tools/tests/test_kr_edge_block_r2.py:202-214 (expected list mirrors implementation). HIGH.

NOT VERIFIED: the edge-smoke CI run; any real proxy answer; the eight service-dependent tests (need field_core in my sandbox).
