VERDICT PASS on 853a5b1eb81d748146d17486ac9d269fb68bea93 (PR 336, Q-08, Lane 15 reviewer, UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. A decode-once guard can disagree with the router on exotic spellings; a miss means the halt call reaches the kill-switch itself.
2. Widening the shapes ("/operator/", "/docs/", "/redoc", "/openapi.json", "/Kill") over-blocks legitimate estates whose host path happens to match.
3. `trust_env=False` silently drops proxy and CA environment for the client.
4. A counter that is only asserted at zero cannot prove the success path leaves it alone.

ASSUMPTIONS: head is current (git ls-remote = full sha above); Python 3.13, httpx 0.28.1; estate topology not visible to me.

REASONING
1. Baseline: kill-switch suite 235 passed, lint test file 21 passed (HIGH, run in scratch worktree).
2. 43 path spellings (case, double and encoded slashes, dot segments, backslash, NUL, leftover %) probed through `_canonical_path` / `_is_self_endpoint` (api.py); each classified as the router would see it (HIGH for the probed set, MEDIUM beyond it).
3. `/kill/` as a shape makes the agent-id check redundant (informational). Main already refuses /kill, /health, /liveness, /heartbeat for any host; the PR adds /Kill, /operator, /docs, /openapi.json, /redoc and encoded forms. Guard is host-independent and README documents it (HIGH).
4. 3xx halt answer now a failed `http_redirect` (HIGH, probed).
5. Mutants: 21 run, 20 killed, 1 survived (counter bumped on SUCCESS too; tests assert 0 only before any ledger write: test_self_guard_c574.py:100, test_halt_result_c811.py:82). Mutant bookkeeping: NOAPPLY not counted as kills; all files restored.
6. merge-tree: clean against main; clean pairwise with PR 344 and PR 347.

FINDINGS
- F-Q08-1 LOW: test gap above; add a success-path assertion that the gap counter stays 0.
- F-Q08-2 LOW: widened over-blocking, intended by the C-574 condition; note in README is sufficient.
- F-Q08-3 LOW: `trust_env=False` ignores proxy environment; README silent on it. Same class as F-Q09-1.
- C-695 casefold condition: closed.

NOT VERIFIED: real GX10 / estate run; CI status; behaviour behind the real edge.

CONCLUSION: PASS. No blocker. Three LOW items for the builder's discretion.
