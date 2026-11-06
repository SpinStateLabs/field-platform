# B-COND-PR439-6825858: head made to contain main, PR 439 new head 6e00e382d6b2

C2 asked for the GX10 16/16 on a head containing main; the GX10 run is the verifier's. I merged origin/main into the branch (no force-push, no conflict) and ran the PR's origin test, 4 passed, plus the other provision_ssl_agents tests in tools/tests (PYTHONUTF8=1; results above in this session, all passing). C1 (CI) runs on this head.
Optional follow-ups for a new PR (card B-FU-PR439-origin-pins): F-439-1 a look-alike host (proxy.test.evil.test, prox.test) and an IPv6 or userinfo case; F-439-2 a non-guarded path on the proxy origin gets no pair, and pair=None sends none. Identity Don Hagell both fields.
