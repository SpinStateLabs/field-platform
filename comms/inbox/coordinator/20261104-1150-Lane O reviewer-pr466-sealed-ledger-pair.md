# Lane O reviewer: PR 466 (C-1181 part 3: sealed-ledger CLI and witness send the operator pair only on a guarded write) @c00dc6c9f8d98b7325194c5bb9643f478cace17e. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head c00dc6c9. Lane A (sealed-ledger). Two commits, both Don Hagell noreply as author and committer (git log, HIGH): c62ccd78 (the change) and c00dc6c9 (a witness rename / anchor commit). The head does NOT contain current main: it is 22 commits behind main cd3b7690 (git rev-list --count pr466..origin/main); `git merge-tree` of the head onto main is clean (HIGH). Source: cli.py +9/-4, witness.py +15/-4, a +90-line test file, one ENVIRONMENT.md anchor. Earlier reviewer reports exist (Lane 7 Q-112 and the C-1194 group seam review); I did not read them and this one is independent. I did not write the head. Claimed through dispatch.sh (R-PR466-c00dc6c).

Objections first: (1) the witness client attaches the pair with `GuardedOperatorAuth`; field-core's own module note (guarded_operator.py, C-877) says that object alone does not stop a followed redirect, so the client must not follow one. witness.py keeps `follow_redirects=False`, but NO test in this PR or in tests/test_witness.py pins it (survivor below): a regression to True would carry the operator pair across a redirect (read, HIGH). (2) the CLI test checks only the HEADERS of a request: nothing asserts the request URL, method or body, so the "path prefix such as /ledger" the function's docstring promises is not actually tested even though the parametrisation includes a /ledger base (read, HIGH). (3) the pair is rebuilt from `auth_headers()` at client construction; the witness test "a pinned test relies on that" ties behaviour to the build time of the client (docstring, HIGH).

Run here (cloud, scratch worktree on c00dc6c9, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 12 passed; the sealed-ledger suite without the subprocess serve test: 814 passed, 5 skipped (101 s). One test, tests/test_operator_observer_c6_serve.py, errors identically on main in this environment (spawns `ledger serve`), excluded. The survivor checks ran the tests that call `_call_served` or build the witness client (test_witness.py, test_caller_signing_f2b.py and the new file).

Mutants on cli.py `_call_served` and witness.py `build_ledger_client` (22 run in a scratch worktree; each against the new file, survivors against the three files above; no syntax-broken kills; I killed and restarted my first sweep once because the survivor check pulled in a baseline-failing test, and the table is the corrected run):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 CLI: the pair only on a guarded ledger route | 5 | 2 | 3 |
| B2 CLI: the request keeps its path prefix, body, timeout and base URL | 4 | 0 | 4 |
| B3 witness: the pair on POST /events only, the secret alone on GET /health | 5 | 5 | 0 |
| B4 witness: no pair in the environment sends the secret alone | 4 | 3 | 1 |
| B5 witness client settings unchanged (timeout, no redirect, transport) | 4 | 2 | 2 |
| Total (counted from the rows) | 22 | 12 | 10 |

Survivors (10): 3 equivalent (forcing the method to POST or the route to "/rotate" for the tested rows gives the same headers because the unguarded row's route and method pair is still unguarded; an unused extra import), 7 real pin gaps:
- F-O-pr466-1 MEDIUM (2 mutants): witness `follow_redirects=True` and `timeout=None` survive (objection 1): the redirect refusal and the 30-second style timeout of the local ledger client are unpinned.
- F-O-pr466-2 MEDIUM-LOW (4 mutants): the CLI request itself is unpinned: `route.lstrip("/")` removed, the body dropped, the timeout changed, and the base URL swapped for another host all survive, because only headers are asserted (objection 2).
- F-O-pr466-3 LOW: an environment with ONE of the two operator variables set: building the pair with `or` instead of `and` survives (a half pair would raise KeyError instead of sending the secret alone).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head REBUILT on current main (the head is 22 commits behind main; the coordinator rebuilds batches, so this is the rebuild condition). C2 pin F-O-pr466-1 in this PR or a recorded follow-up (a test that the witness local client does not follow a redirect: it carries the operator pair).
Optional, NEW PR after the head is frozen: F-O-pr466-2 and F-O-pr466-3.

Tokens/cost line: not available to me. I do not know.
