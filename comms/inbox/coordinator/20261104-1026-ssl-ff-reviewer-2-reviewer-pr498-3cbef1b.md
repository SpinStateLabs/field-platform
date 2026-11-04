# Reviewer report: PR 498 @3cbef1b5 (lifecycle-manager sweep windows 1..3650 days, scout P-11)

Reviewer: ssl-ff-reviewer-2. All runs UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH with ':' separator.

## Verdict: PASS WITH CONDITIONS (head 3cbef1b595c1a43ef4e0fbd9028d1e753e5abf69)
Conditions: C1 rebase on current main (PR base is cd3b7690, main is 97dcfec1, conflict not checked); C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking code finding. F1 (CLI lower bound unpinned) is optional LOW and goes in a new PR if wanted.

## Objections first
1. 3650 days is a policy number (the PR says Don may change it). A legitimate longer window, for example a 20-year reattest cycle, now gets 422 over HTTP and exit 2 from the CLI. Behaviour change for manual callers; the scheduled tick uses defaults 30 and 90 (PR docstring; I grepped the repo: no caller or doc uses a 4-digit window) (MEDIUM, owner ruling).
2. The CLI gained `min=1`; before the PR the CLI accepted 0 and negatives. The tests pin only the CLI upper bound and an accepted 1; the lower bound is unpinned (F1, run) (HIGH).
3. The CLI constant is a copy of the API constant, not an import; drift is caught only by the equality test (killed by K1/K2) (HIGH).
4. Test depends on typer's rich error panel text and strips ANSI; a typer upgrade that reflows the panel could split the option name across lines (LOW, reading only).

## Scope and identity
3 files: lifecycle_manager/api.py (+7/-2), cli.py (+5/-2), tests/test_sweep_request_bounds.py (new, 100). No docs change. 2 commits, author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head) test_sweep_request_bounds.py: 23 passed. Full lifecycle-manager suite: 292 passed. Environment note: I installed typer into my own interpreter; no repo file changed.

## Mutants (api.py, cli.py; kill = test_sweep_request_bounds.py fails; baseline 23 passed so every kill is real)
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| A1 | api upper | expiry le removed | KILLED |
| A2 | api upper | reattest le removed | KILLED |
| A3 | api upper | expiry le = bound+1 | KILLED |
| A4 | api upper | reattest le = bound-1 | KILLED |
| A5 | api upper | expiry lt, not le | KILLED |
| A6 | api lower | expiry ge=0 | KILLED |
| A7 | api lower | reattest ge removed | KILLED |
| A8 | api lower | expiry gt=1 | KILLED |
| K1 | shared bound | api constant 36500 | KILLED |
| K2 | shared bound | cli constant 3000 | KILLED |
| C1 | cli upper | expiry max removed | KILLED |
| C2 | cli upper | reattest max removed | KILLED |
| C3 | cli upper | expiry max 10**9 | KILLED |
| C4 | cli upper | reattest max bound+1 | KILLED |
| C5 | cli upper | expiry max bound-1 | KILLED |
| C6 | cli lower | expiry min removed | SURVIVED (real, LOW, F1) |
| C7 | cli lower | reattest min removed | SURVIVED (real, LOW, F1) |
| C8 | cli lower | expiry min=0 | SURVIVED (real, LOW, F1) |

Counted from the table: 18 rows (api upper 5, api lower 3, shared bound 2, cli upper 5, cli lower 3). KILLED 15, SURVIVED 3, none equivalent. Kill rate 15 of 18 = 83%. Per behaviour: api upper 5/5, api lower 3/3, shared bound 2/2, cli upper 5/5, cli lower 0/3.

## Findings
- F1 LOW (HIGH confidence, run): C6, C7, C8. Nothing refuses `--expiry-days 0` or `--reattest-days -1` at the CLI. Add a parametrised test mirroring the upper-bound CLI test with values "0" and "-1", exit code 2 and option name in the output. New PR.
- F2 LOW (MEDIUM): the CLI bound is a copy; importing api.MAX_SWEEP_DAYS in cli.py would remove the drift risk, but the CLI may avoid importing the API module on purpose; I do not know.

## Not verified
Rebase on 97dcfec1; CI; GX10; typer version behaviour in CI colour mode (the PR says it reproduced with GITHUB_ACTIONS=true; I did not).
