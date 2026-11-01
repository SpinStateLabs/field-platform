VERDICT PASS on 3725870232722506b677e8b63fa6448f0be17427 (PR 347, Q-10, Lane 15 reviewer, UNVERIFIED: cloud, no GX10, no CI logs, no real edge)

OBJECTIONS (first)
1. `_ask` uses `urllib.request.urlopen`, which follows redirects: a pass-through answering 301 to a path the edge refuses is reported as refused, masking it.
2. The informational shapes (`_informational`) fail only on a 2xx; a service 401 or 5xx on them passes silently, so they prove little.
3. Status 0 (connection error) is a fail-closed problem for gating shapes but only an "info" line for informational ones.
4. Shapes are built with string replace on the route; a route rename would make a shape equal another and silently shrink coverage.

ASSUMPTIONS: head current; no real Caddy edge available to me.

REASONING
1. Baseline tools/tests/test_kr_edge_block_r2.py: 52 passed (HIGH). (First attempt with a short PYTHONPATH gave 8 failures from missing service paths; rerun with all services/*/src green.)
2. Stub-server probe (HIGH): gating shape answered 200 or 401 = 1 problem; edge-403 = 0; gating 301 to the plain path = 0 problems (objection 1 confirmed); info shape 200 = problem; info 401/500/301-then-403 = 0 problems.
3. `check` requires status 403 and body == EDGE_BODY for gating shapes (check_edge_block.py:108, 114); 24 gating shapes (_variants), 2 informational (4 with a prefix).
4. Mutants: 16 run, 16 killed (drop 403, drop body check, no XFF spoof, info 2xx threshold x3, status0-ok, each dropped shape, info loop, leaks dropped); NOAPPLY none; file restored (diff clean).
5. merge-tree: clean vs main and pairwise with PR 336 and PR 344.

FINDINGS
- F-Q10-1 LOW: redirects followed in `_ask`; use a no-redirect opener so a 3xx from a gating shape is a problem. Test the 301 case.
- F-Q10-2 LOW: informational shapes only catch 2xx, by design and documented; promote to gating once CI logs show 403 everywhere.
- F-Q10-3 LOW: no test asserts shape count against route renames.

NOT VERIFIED: behaviour against the real edge; CI log of the "info:" lines.

CONCLUSION: PASS. No blocker; F-Q10-1 is worth a follow-up card.
