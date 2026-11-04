# Review PR 464 @ b8ff923e6abe50797daab2c09aadde68ceb2be50 (C-1181 part 2) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head b8ff923e. UNVERIFIED (cloud, no GX10; the coordinator's GX10 16/16 and CI are still required).

## Objections raised first (FORCE O)
1. The tests might pin only the happy path and let a header leak survive. Tested below: 21 mutants.
2. The hand-copied route table could drift from the receiver. Pinned both directions by `test_the_cli_table_equals_the_routes_the_broker_guards` (guard_dependent_routes); mutants B5a-d kill it.
3. A contract_id containing "/" would not match `[^/]+`, so the pair is dropped and the write is refused (fail closed, not a leak). Not pinned. LOW, no action (F-R464-1).
4. The head is built on 6385f877, not current main 97dcfec1. `git merge-tree` against 97dcfec1 is clean; no change under services/federation-broker or guarded_operator.py between the two (HIGH). Coordinator still re-runs on the rebased head.

## Facts (HIGH unless tagged)
- Head fetched via refs/pull/464/head = b8ff923e; 1 commit; author AND committer both Don Hagell <13129187+dhagell@users.noreply.github.com>.
- Diff: cli.py swaps `auth_headers()` for `_hdr(method, path)` -> `field_core.guarded_operator.request_headers` on all three requests; adds `FEDERATION_TEMPLATES = (("PUT","/contracts/{contract_id}"),)`; new test file with 2 tests. The old `auth_headers` import is removed; no other use in cli.py (viewed).
- Baseline, unmutated: new test file 2 passed; whole federation-broker suite 193 passed (PYTHONPATH relative `../../packages/field-core/src:../sealed-ledger/src:src`, Python 3.13, fresh venv). Nothing was a baseline failure, so nothing is miscounted as a kill.

## Mutants (new test file; mutation script run in a scratch worktree, cli.py restored after)
| Behaviour | ID | Mutation | Result |
|---|---|---|---|
| B1 PUT carries the pair | B1a | PUT sends perimeter only | KILLED |
| | B1b | PUT sends no headers | KILLED |
| | B1c | PUT path `/contract` (no match) | KILLED |
| | B1d | PUT call uses method GET | KILLED |
| | B1e | table empty | KILLED |
| B2 GET /contracts has no pair | B2a | GET uses auth_headers() | KILLED |
| | B2b | GET call marked PUT | KILLED |
| | B2c | table adds GET /contracts | KILLED |
| | B2d | GET sends no headers | KILLED |
| B3 POST /crossing has no pair | B3a | crossing uses auth_headers() | KILLED |
| | B3b | table adds POST /crossing | KILLED |
| | B3c | crossing sends no headers | KILLED |
| | B3d | crossing call marked PUT | KILLED |
| B4 perimeter secret always | B4a | non-PUT returns {} | KILLED |
| | B4b | secret dropped on PUT | KILLED |
| | B4c | `_hdr` returns {} | KILLED |
| | B4d | secret dropped on GET | KILLED |
| B5 table equals receiver guarded routes | B5a | wrong path template | KILLED |
| | B5b | extra non-route DELETE entry | KILLED |
| | B5c | POST instead of PUT | KILLED |
| | B5d | GUARDED compiled from empty | KILLED |

Totals counted from the table: 21 rows, 21 KILLED, 0 SURVIVED, 0 anchor failures. No survivor, so no whole-suite survivor run was needed (the script runs one automatically; none triggered).

## Findings
- F-R464-1 LOW: no test for a contract_id with "/" or other path-special characters. Behaviour fails closed (pair omitted, receiver refuses under ENFORCE). Optional, NEW PR only; the head is frozen after PASS.
- F-R464-2 LOW (inherited, out of scope): httpx module-level calls still read the process proxy environment; owned by C-487 per the guarded_operator.py docstring (HIGH, read from file).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main before merge (PROTOCOL).
