# Lane O reviewer: MERGE 9 (batch ma3; main 9addf44f to c4ac8c14; PRs 334, 335, 347; 13 commits), ROLE-LOOP FALLBACK, read-only. PARTIAL. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main) for the CODE part, the edge-block checker integration/demo/fixtures/kr-edge/check_edge_block.py and tools/tests/test_kr_edge_block_r2.py (commits 28989506 to c4ac8c14), naming the merged head c4ac8c14. NOT COVERED, "I do not know": the four ADR note commits (d1126482, b4df543f, 48278821, c22bb274: ADR 02 and ADR 07 notes of what the sentinel and crosswalk code do); I did not check those notes against the code. All 13 commits: Don Hagell noreply as author and committer (git log 9addf44f..c4ac8c14, HIGH). There was no WORKLIST item for MERGE 9; I took it as the oldest merged batch without a reviewer note (no claim lock exists for it, so another reviewer could duplicate: coordinator please add the line or mark it done).

Objections first: (1) the checker proves the EDGE's 403 for 24 path shapes per route; shapes the builder lists as not probed (other methods, other host encodings, absolute-form target, a non-loopback peer that must reach the service) stay unproven, as the docstring says (read, HIGH). (2) four shapes are "informational": they fail the check only on a 2xx, so a 3xx, 4xx or 5xx pass-through from a service does not turn CI red (by design, C-671); a real bypass answered with a non-2xx status (a 401 or 400 from the service itself) would only print an `info:` line. (3) `_open` builds a new opener for every request (cost only).

Run here (cloud, scratch worktree on c4ac8c14, relative PYTHONPATH of every service src and packages src): tools/tests/test_kr_edge_block_r2.py 60 passed (without the PYTHONPATH, 8 per-service tests error at setup: environment, not the PR). NOT run: the 16-suite set, CI, a real Caddy.

Mutants on check_edge_block.py (37 run in a scratch worktree, each against the test file; no syntax-broken kills; the test file carries its own MUTANTS table, so some kills overlap with it, but every mutant below is mine):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 the 15 extra C-27 shapes are sent (drop, re-case or alter one) | 5 | 5 | 0 |
| B2 the four extra gating shapes of C-1062 | 4 | 4 | 0 |
| B3 informational shapes: reported, fail only on 2xx | 5 | 5 | 0 |
| B4 fail closed: no answer is never a refusal, exit 1 on any problem | 5 | 5 | 0 |
| B5 the summary counts gating requests and informational shapes apart | 4 | 4 | 0 |
| B6 a 3xx is the answer, never followed | 4 | 3 | 1 |
| B7 the opener ignores the proxy environment | 4 | 4 | 0 |
| B8 ten second timeout on every request | 2 | 2 | 0 |
| B9 spoofed X-Forwarded-For on the plain path and the secret on the wire | 4 | 4 | 0 |
| Total (counted from the rows) | 37 | 36 | 1 |
B8 has 2 mutants (under 4): a timeout has few distinct wrong values.

Survivor (1, equivalent): reversing the handler list passed to build_opener; urllib sorts handlers by handler_order, so the order does not matter (read, MEDIUM).

CONDITIONS (none blocking; on main): C1 the four ADR note commits need a reader who checks each cited symbol and count against the sentinel and crosswalk code of that commit (a docs-vs-code card). C2 coordinator: a WORKLIST line or a done note for MERGE 9 so it is not reviewed twice.

Tokens/cost line: not available to me. I do not know.
