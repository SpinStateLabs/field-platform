# Reviewer report: PR 593 @4ad73523 (tests(claude-approver): config helpers, decode_reason and halt_open_paths, scout S2-7)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator) with the service's `tests` directory added for the shared fakes. Tests-only PR: services/claude-approver/tests/test_approver_config_helpers.py (+212).

## Verdict: PASS WITH CONDITIONS (head 4ad7352384fecaef46347d1a771c016e5490f84d)
Conditions: C1 rebase check on current main: the PR base is 97dcfec1 and main is now b963407a; `git merge-tree` of the two shows a clean tree (506df4e3), but I did not run the rebased head; C2 GX10 16/16 on the exact head and CI green. No blocking finding; the new tests are green on the head and kill 29 of 30 non-equivalent mutants.

## Objections first
1. Tests that pin implementation quirks (a trailing-slash strip, a `./var` default) become friction when a default is deliberately changed; here each pinned default is the code's documented one (config.py read, HIGH).
2. `read_secret_file` is the one function that touches secret files; the tests pin "never raises" for a missing file, a directory, invalid UTF-8, a blank file and an embedded NUL path, but not a file the process cannot read (permission denied) (MEDIUM, reasoned: that branch is the same `OSError` handler, killed by R5 for the missing-file case).
3. The late-id test pins the DOCUMENTED limitation that an agent added to the map after `create_app` answers 401 until restart; if that limitation is ever fixed on purpose the test must change in the same commit (HIGH, read of halt_open_paths docstring and the test).
4. The two paths the tests do not name: `poll_seconds`, `halt_wait_seconds` and `_float_env` (config.py:38-53) remain untested by this file (HIGH, read; the PR does not claim them).
5. I read the production code for the helpers; one function of the PR's scope (`decode_reason`) is a one-liner whose correctness depends on `urllib.parse.unquote` replacement semantics for invalid UTF-8 (HIGH, pinned by X7).

## Scope and identity
1 file, 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No production code touched. No secret, address or flag value in the test (HIGH, read).

## Runs
Baseline (unmutated head): test_approver_config_helpers.py 35 passed; full claude-approver suite 350 passed. Mutants edit config.py, core.py and api.py one at a time; kill = the new file fails; for survivors I ran the full suite; files restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| R1 | read_secret_file | content not trimmed | KILLED |
| R2 | read_secret_file | blank content returned as empty string | KILLED |
| R3 | read_secret_file | `UnicodeDecodeError` dropped from the except tuple | SURVIVED, EQUIVALENT (UnicodeDecodeError is a subclass of ValueError, which stays in the tuple) |
| R4 | read_secret_file | embedded NUL raises (ValueError dropped) | KILLED |
| R5 | read_secret_file | missing file raises (OSError dropped) | KILLED |
| R6 | read_secret_file | decoded as latin-1 | KILLED |
| R7 | read_secret_file | leading whitespace kept (rstrip) | KILLED |
| R8 | read_secret_file | only spaces trimmed, newline kept | KILLED |
| K1 | key file | presence inverted | KILLED |
| K2 | key file | key path env not stripped | KILLED |
| K3 | key file | no default key file | KILLED |
| E1 | environment filter | not stripped | KILLED |
| E2 | environment filter | blank filter is an empty string | KILLED |
| U1 | service_url | trailing slash kept | KILLED |
| U2 | service_url | env value not stripped | KILLED |
| U3 | service_url | default not rstripped | KILLED |
| U4 | service_url | blank env does not fall back | KILLED |
| U5 | service_url | also strips trailing spaces after the slashes (control) | SURVIVED, EQUIVALENT (env value is stripped first; whole suite 350 passed) |
| D1 | data_dir | not stripped | KILLED |
| D2 | data_dir | default changed to ./data | KILLED |
| X1 | decode_reason | no percent-decoding | KILLED |
| X2 | decode_reason | cut before decoding | KILLED |
| X3 | decode_reason | no cut | KILLED |
| X4 | decode_reason | None becomes the empty string | KILLED |
| X5 | decode_reason | plus decoded as space (`unquote_plus`) | SURVIVED (LOW, F1; full suite 350 passed) |
| X6 | decode_reason | limit off by one | KILLED |
| X7 | decode_reason | invalid UTF-8 escape raises (strict) | KILLED |
| H1 | halt_open_paths | returns an empty set | KILLED |
| H2 | halt_open_paths | path lacks the id | KILLED |
| H3 | halt_open_paths | wildcard path also open | KILLED |
| H4 | halt_open_paths | create_app opens no path | KILLED |
| H5 | halt_open_paths | create_app passes None | KILLED |

Counted from the table: 32 rows (read_secret_file 8, key file 3, environment filter 2, service_url 5, data_dir 2, decode_reason 7, halt_open_paths 5). KILLED 29, SURVIVED 3 (R3 and U5 equivalent, X5 real). Kill rate on non-equivalent rows 29 of 30 = 97%. Per behaviour: read_secret_file 7/7 non-equivalent, key file 3/3, environment filter 2/2, service_url 4/4 non-equivalent, data_dir 2/2, decode_reason 6/7, halt_open_paths 5/5.

## Findings
- F1 LOW (HIGH confidence, run): X5. A "+" in a kill-reason header decodes as a plus today; nothing pins that (`unquote_plus` would turn it into a space). Add `decode_reason("a+b") == "a+b"`.
- F2 LOW: objection 2, permission-denied is not tested separately.
- F3 INFO: R3 and U5 are equivalent by Python semantics, not test gaps.

## Not verified
Rebased run on b963407a; CI; GX10; `poll_seconds`, `halt_wait_seconds`, `_float_env` (out of the PR's claim).
