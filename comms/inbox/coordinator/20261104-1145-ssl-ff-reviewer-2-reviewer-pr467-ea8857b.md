# Reviewer report: PR 467 @ea8857b7 (conformance-sentinel per-request operator pair, secret-only reads, C-1180, C-1150 F2 slice B)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Credential-header code.

## Verdict: PASS WITH CONDITIONS (head ea8857b74026f67317b52e1da8fb952e161b4dbd)
Conditions: C1 pin the CLI wiring (F1, MEDIUM): five of the eight sites the PR changes are in cli.py and nothing but an "auth_headers is absent" scan covers them; a one-test CliRunner or a call-site check closes it (a condition fix may be pushed; the rest of the head stays frozen); C2 rebase on current main (PR base is 6385f877, main is 97dcfec1, conflict not checked, three files also touch ENVIRONMENT.md and tools/tests/http_env_proxy_allowlist.txt); C3 GX10 16/16 on the exact rebased head; C4 CI green.

## Objections first
1. cli.py `check` and `clauses` (both now `perimeter_headers()`) and `score` (the three clients now built by `headers.py`) have no behavioural test. Swapping the sentinel, registry and delegation clients for one another, or dropping the secret, passes every test (W1 to W5 below, run, also against the full existing sentinel suite: 280 passed with each mutant) (HIGH).
2. The new `headers.py` carries a second copy of the operator-pair header names (`_OPERATOR`, `_KEY`, line ~21 of headers.py) "not imported: this service does not apply operator auth". If field-core renames either header, this copy drifts silently; the test imports the names from operator_auth so a rename would turn the guarded-write test red, which covers it (MEDIUM, by reading).
3. `_pair()` reads the environment when a client is built, not per request. The test name says "per-request"; the pair is bound at client construction and `GuardedOperatorAuth` decides per request whether to attach it. A rotated env pair is not picked up by an existing client (MEDIUM, by reading; I did not run a rotation).
4. S1 (the sentinel client built like the registry client) survives: for the paths the sentinel serves, /health and /check, no registry-guarded path matches, so the behaviour is equivalent unless the client calls `POST /agents`. Low value (LOW).
5. Foreign-origin refusal is bound to `base` and pinned (F1 killed) (HIGH).

## Scope and identity
7 files: conformance_sentinel cli.py (+8/-5), engine.py (+3/-3), governed.py (+2/-2), headers.py (new, 45), docs/ENVIRONMENT.md (anchor line), tools/tests/http_env_proxy_allowlist.txt (cli.py::score x3 replaced by three headers.py entries), tests/test_per_request_headers_c1180.py (new, 128). 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). Test ids and keys are marked made-up (HIGH, read).

## Runs
Baseline (unmutated head): PR test file 17 passed; full conformance-sentinel suite 280 passed (typer installed in my interpreter); tools `test_http_env_proxy_lint_c57.py`, `test_operator_plumbing.py`, `test_proxy_url_required_c285.py` 120 passed, 1 skipped. Mutants one at a time; kill = the PR test file fails; the CLI group W also run against the full sentinel suite.

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| E1 | engine/governed clients | governor status client sends the pair | KILLED |
| E2 | engine/governed clients | introspect client sends the pair | KILLED |
| E3 | engine/governed clients | Governor client sends no secret | KILLED |
| E4 | engine/governed clients | governor status client sends no secret | KILLED |
| E5 | engine/governed clients | Governor client adds a pair | KILLED |
| S1 | sentinel client | built with the registry guard | SURVIVED (equivalent for /health and /check, LOW) |
| S2 | sentinel client | sends the pair on every call | KILLED |
| S3 | sentinel client | sends no secret | KILLED |
| S4 | sentinel client | transport argument ignored | KILLED |
| R1 | registry client | uses the delegation table | KILLED |
| R2 | registry client | never gets the pair | KILLED |
| R3 | registry client | sends the pair on every call | KILLED |
| R4 | registry client | sends no secret | KILLED |
| R5 | registry client | empty table, never a pair | KILLED |
| D1 | delegation client | uses the registry table | KILLED |
| D2 | delegation client | never gets the pair | KILLED |
| D3 | delegation client | sends the pair on every call | KILLED |
| D4 | delegation client | sends no secret | KILLED |
| F1 | foreign origin | auth bound to an empty base | KILLED |
| T1 | tables | exported registry table wrong | KILLED |
| W1 | cli wiring | `check` sends no secret | SURVIVED (also by the full sentinel suite) |
| W2 | cli wiring | `clauses` sends no secret | SURVIVED (also by the full suite) |
| W3 | cli wiring | `score` sentinel client is a registry client | SURVIVED (also by the full suite) |
| W4 | cli wiring | `score` registry client has no secret and no pair | SURVIVED (also by the full suite) |
| W5 | cli wiring | `score` delegation client is a registry client | SURVIVED (also by the full suite) |
| A1 | no auth_headers (ast test) | unused auth_headers import in engine | KILLED |
| A2 | no auth_headers (ast test) | auth_headers attribute in governed | KILLED |

Counted from the table: 27 rows (engine/governed 5, sentinel client 4, registry 5, delegation 4, foreign origin 1, tables 1, cli wiring 5, ast 2). KILLED 21, SURVIVED 6 (S1 equivalent-ish, W1 to W5 real). Kill rate 21 of 27 = 78%; on the 22 rows outside the CLI wiring group 21 of 22 = 95%. Per behaviour: engine/governed 5/5, sentinel 3/4, registry 5/5, delegation 4/4, foreign origin 1/1, tables 1/1, ast 2/2, cli wiring 0/5.

## Findings
- F1 MEDIUM (HIGH confidence, run): W1 to W5, objection 1. The CLI is where an operator's secret leaves the process by hand; five sites unpinned. Condition C1.
- F2 LOW: objection 2, the duplicated header-name constants.
- F3 LOW: objection 3, the pair is bound at client construction; docstring and test name say "per request".
- F4 LOW: S1.

## Not verified
Rebase on 97dcfec1; CI; GX10; a live registry or delegation service (all calls went through httpx MockTransport).
