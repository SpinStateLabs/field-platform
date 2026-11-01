# B-02: tools/tests speed pass (proposal only, no edits) - builder Lane 16

Measured on main acaf5f2, GX10 (load about 1), serial, `pytest -q tools/tests --junitxml`: 3255 passed, 4 skipped, 504 s wall; per-testcase times sum to 503.1 s over 53 test modules. Source: junit XML from that run (HIGH).

## Objections
1. Times are one run on one host; a single run can be off by a few percent (MEDIUM).
2. Splitting files does not cut serial wall time; only parallel execution or fewer subprocess launches does.
3. A split that drops mutant cases loses coverage the cards paid for.

## Five slowest modules (share of 503.1 s)
| module | s | share | tests |
|---|---|---|---|
| test_topology_lint.py | 108.8 | 22% | 287 |
| test_phase_g_check.py | 104.3 | 21% | 106 |
| test_renew_token.py | 75.0 | 15% | 183 |
| test_fly_identity_c5.py | 65.9 | 13% | 87 |
| test_estate_probe.py | 37.8 | 8% | 128 |

The five are 79% of the suite (391.8 s). Next: test_operator_cli_c2 21.4 s, test_estate_kill_watcher 16.0 s.

## Observed pattern (from `--durations=40`, same head)
- topology_lint: many parametrized cases sit at about 2.0 s each (U07, U08b, U09, U22, the entrypoint-bypass cases): a per-case floor, not a few heavy tests.
- fly_identity_c5: each C-5 mutant case about 4.0 s; five tests at 4.0 to 6.0 s.
- renew_token: individual tests 2 to 6.5 s; 20 of the top 40.
- phase_g_check: FAULT cases 2 to 6.3 s.
I did not read the test bodies to say why each case costs 2 s or 4 s; that is the first step of the work (LOW on cause).

## Proposed split (not applied)
1. CI only: run these five modules as their own parallel jobs (or `pytest-xdist -n 4` where the host has cores); wall time then tracks the slowest module (108.8 s) plus the rest (about 111 s), roughly 220 s versus 504 s, if cases are independent (MEDIUM; unmeasured; ports and temp dirs must not collide).
2. Per module, find the per-case fixed cost (subprocess start, `sleep`, process-tree kill wait) and share it through one module-scoped fixture; pin the same mutants. Start with topology_lint (287 cases at the 2 s floor) and c5 (4 s per mutant).
3. Do not split files for speed; keep the file boundaries cards and mutants refer to.

Not done: no branch, no PR, no test change. Owner decision: whether a CI parallelism card (item 1) is wanted. Reviewer: none needed for a proposal.
