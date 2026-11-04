# Reviewer report: PR 460 @3040d198 (lifecycle CLI: no-proxy, no-redirect estate clients and --cacert; 344 + 425 rebuilt, C-1171)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Credential-carrying clients, TLS option.

## Verdict: PASS WITH CONDITIONS (head 3040d19854e302801e393e8981919b0d1d9f0009)
Conditions: C1 rebase on current main (PR base is b39287c1, main is 97dcfec1, 11 merges behind in STATUS terms; conflicts not checked: cli.py, api.py, README, runbook and http_env_proxy_allowlist.txt are all touched by other batches); C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking code finding; the verification-off paths are all pinned (B2, B3, B5, B6 killed).

## Objections first
1. README states the bundle REPLACES the trust store, "does not add to it" (services/lifecycle-manager/README.md, new paragraph). No test pins that: a mutant that ADDS the bundle to the system store (B4) passes all 51 tests (HIGH, run). The claim is true in the code as written (`ssl.create_default_context(cafile=...)` loads only the cafile) (HIGH, read).
2. The refusal message is documented as echoing neither path nor content; a mutant that echoes the SSL error text (B8) survives. For a malformed PEM the stdlib error text is generic, so the exposure is small, but it is unpinned (MEDIUM, run).
3. `--cacert` replaces the system store, so an operator who passes a private CA loses trust in public CAs for that run; stated in README and help (HIGH, read). Intentional per Don's ruling on F-Q09-1 (cited in the commit, not verified here).
4. The file-existence option flags `exists=True` and `dir_okay=False` are unpinned (O1, O2). `_verify_from` still refuses a missing or directory path through OSError, so the outcome is a different message and possibly exit code, not an unsafe state (MEDIUM, reasoned; I did not run the CLI against a missing path).
5. The PR bundles two rebuilt PRs (344, 425) and a doc commit: 6 commits, 7 files, 701 added lines; the review surface is wide for one verdict (HIGH).
6. `serve` verb clients are out of scope, stated in README "separate, open item (C-487)" (HIGH, read).

## Scope and identity
7 files: cli.py (+65/-... net), api.py (docstring), README.md (+8), runbook (6 lines), http_env_proxy_allowlist.txt (12 lines), two new test files (232 + 397). 6 commits; author AND committer on all six = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). Tests use a throwaway in-process CA on loopback; made-up secret, no estate value (HIGH, read).

## Runs
Baseline (unmutated head): test_cli_cacert_c1098.py + test_cli_clients_no_proxy_c575.py 51 passed (about 44 s); tools test_http_env_proxy_lint_c57.py 101 passed. Mutants one at a time on cli.py with `-x`; kill = either file fails. File restored after each (git status checked after the run).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| A1 | no proxy/redirect | trust_env True | KILLED |
| A2 | no proxy/redirect | trust_env not set | KILLED |
| A3 | no proxy/redirect | redirects followed | KILLED |
| A4 | no proxy/redirect | follow_redirects not set | KILLED |
| A5 | pair/secret | perimeter secret dropped | KILLED |
| A6 | pair/secret | pair never sent | KILLED |
| A7 | pair/secret | guarded routes empty | KILLED |
| A8 | pair/secret | auth base unbound | KILLED |
| B1 | cacert verify | verify= dropped from the client | KILLED |
| B2 | cacert verify | default returns False (verification off) | KILLED |
| B3 | cacert verify | bundle ignored, system store | KILLED |
| B4 | cacert verify | bundle ADDS to the store | SURVIVED (F1) |
| B5 | cacert verify | bad PEM falls back to system store | KILLED |
| B6 | cacert verify | bad PEM turns verification off | KILLED |
| B7 | cacert verify | message echoes the path | KILLED |
| B8 | cacert verify | message echoes the SSL error text | SURVIVED (F2) |
| B10 | cacert verify | _service_client default verify False | KILLED |
| B11 | cacert verify | estate_clients default verify False | KILLED |
| W1 | verb wiring | sweep forgets cacert | KILLED |
| W2 | verb wiring | provision forgets cacert | KILLED |
| W3 | verb wiring | decommission forgets cacert | KILLED |
| W4 | verb wiring | _provision_clients ignores cacert | KILLED |
| W5 | verb wiring | governor client misses verify | KILLED |
| W6 | verb wiring | killswitch client misses verify | KILLED |
| W7 | verb wiring | ledger client misses verify | KILLED |
| W8 | verb wiring | delegation client misses verify | KILLED |
| W9 | verb wiring | registry client misses verify | KILLED |
| O1 | option | exists=True removed | SURVIVED (F3) |
| O2 | option | dir_okay=False removed | SURVIVED (F3) |
| O3 | option | option renamed | KILLED |

(B9, "drop 'nothing sent'", did not apply: the text occurs 6 times; not counted. Id B9 is therefore absent.)

Counted from the table: 30 rows (no proxy/redirect 4, pair/secret 4, cacert verify 10, verb wiring 9, option 3). KILLED 26, SURVIVED 4, none equivalent. Kill rate 26 of 30 = 87%. Per behaviour: no proxy/redirect 4/4, pair/secret 4/4, cacert verify 8/10, verb wiring 9/9, option 1/3.

## Findings
- F1 MEDIUM (HIGH confidence, run): B4, objection 1. A README promise with no pin. A test would need a leaf signed by a CA the system store trusts; if not feasible, a unit assertion that the returned context's `cert_store_stats()["x509_ca"]` equals the number of certs in the bundle.
- F2 LOW: B8.
- F3 LOW: O1, O2.

## Not verified
Rebase on 97dcfec1; CI; GX10; the ruling text of F-Q09-1; behaviour with a missing or directory `--cacert` through the real CLI.
