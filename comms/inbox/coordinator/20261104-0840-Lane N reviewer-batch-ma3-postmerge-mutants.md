# Reviewer (read-only, post-merge, FALLBACK): MERGE 9 = batch ma3, main 9addf44f -> c4ac8c14 (PRs 334 @8bea8c4, 335 @fc73f64, 347 @8dae2b3; 13 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `c4ac8c14`.** The record gates (13 commits, a fast-forward, 0 nonconforming identities, verifier A 16/16 on the head, verdicts naming the heads, CI 7/7, pointer comments) are in my C-1141 audit (`20261104-0830-reviewer-laneA-c1141-merge9-12-15-audit.md`); this file adds the MUTATION read of the code the batch changed. The queue was EMPTY, so this is the ROLE-LOOP fallback (the oldest merged batch with no mutation note).

Diff (HIGH, read): `integration/demo/fixtures/kr-edge/check_edge_block.py` (+72/-7) and `tools/tests/test_kr_edge_block_r2.py` (+274), `tools/tests/http_env_proxy_allowlist.txt` (-1), two ADR notes (docs).

## Objections first
1. The checker is a security gate (does the edge refuse the two internal routes?) that must FAIL CLOSED: the failure shape is a green run that did not ask, so I mutated every place it could say "ok" without having asked.
2. The perimeter secret is sent to a URL the caller chose; its docstring says it is "never argv, never printed". That claim has the weakest pin (X1 below).
3. "Not yet proven" informational shapes fail only on a 2xx: a deliberately lenient class, documented in the file.

## Measured (GX10 ~/ff-work/wt-ma3 at c4ac8c14, python -B, own venv, service src on PYTHONPATH)
`tools/tests/test_kr_edge_block_r2.py`: 60 passed (the first run showed 8 failures from `ModuleNotFoundError` for the sibling services in my venv, environment only).

## Mutants (42 rows; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| G1 all 24 gating shapes per route are sent | 7 | 0 |
| I1 informational shapes are sent and fail only on a 2xx | 8 | 0 |
| R1 a 3xx is the answer, not a pointer to follow | 4 | 0 |
| P1 the opener ignores the proxy environment | 3 | 1 (gap: an `https` proxy in `ProxyHandler`; no test uses an https base) |
| S1 a non-403 answer or a wrong body fails | 4 | 1 (gap: `EDGE_BODY` shortened to `"internal route"`; the tests use the module constant, so the literal text is unpinned) |
| C1 the summary counts gating requests only | 4 | 1 (gap: `refused` minus the informational leaks; no test has an informational 2xx and reads the summary) |
| E1 fails closed (network error, exit 1, exit 2) | 5 | 0 |
| X1 the perimeter secret goes in a header, never printed | 2 | 2 (**gap**: a `print(secret)` and a secret in the `::error::` line both pass) |
Totals counted from the table: killed 7+8+4+3+4+4+5+2 = 37; survived 0+0+0+1+1+1+0+2 = 5; 42 rows. All 5 survivors are real unpinned details, none equivalent.

## Conditions
- C1: none blocking (merged; the gate itself fails closed under every mutant that could make it say ok).

## Findings (non-blocking; new PR only)
- F-ma3-1 MEDIUM-LOW: pin that the secret never appears in stdout or stderr (X1): run `check` with a made-up `FIELD_SHARED_SECRET` and assert the captured output does not hold it, on both a pass and a failing run.
- F-ma3-2 LOW: assert the literal edge body text (S1), an https base or proxy dict (P1), and the summary line with an informational 2xx (C1).
