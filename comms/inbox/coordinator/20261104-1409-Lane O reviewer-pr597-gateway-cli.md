# Lane O reviewer: PR 597 (force-gateway CLI: an unknown preset exits 2 with the known ones; telemetry errors are named) @a3db18d5a3488125b8b2e9f434ad456871e2f4b4. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head a3db18d5. Lane A (force-gateway). One commit, Don Hagell noreply (numeric form) as author and committer (git log, HIGH). The head is 1 commit behind origin/main 97dcfec1 (git rev-list --count pr597..origin/main); a merge was not tested. Files: force_gateway/cli.py +15/-2, test_cli_presets_telemetry.py +102. I did not write the head. Claimed through dispatch.sh (R-PR597-a3db18d).

Objections first: (1) the unknown-preset message deliberately does not repeat the caller's name ("unknown preset; choose from ..."), which is the opposite of the HTTP route `/presets/{name}` (PR 527 pinned that route echoing the name as a repr, my report 20261104-1014); the CLI and the route now follow different rules for the same input (read, HIGH). (2) `telemetry` prints the response body verbatim on a 200 and nothing of the body otherwise: a body that is not JSON or is huge is printed whole (no cap here; read, HIGH). (3) the CLI sends the perimeter header from `auth_headers()` (the operator pair included, if the environment has one) to every telemetry call; the new tests do not look at the headers (survivor below).

Run here (cloud, scratch worktree on a3db18d5, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 25 passed; whole force-gateway suite 473 passed. NOT run: the 16-suite set, CI.

Mutants on force_gateway/cli.py (24 run in a scratch worktree; each against the new test file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 an unknown preset exits 2 on stderr and lists the known ones, repeating nothing | 6 | 4 | 2 |
| B2 a known preset prints its block | 4 | 3 | 1 |
| B3 telemetry: an unreachable gateway is exit 1, class name only | 5 | 5 | 0 |
| B4 telemetry: a non-200 is exit 1, status only | 5 | 4 | 1 |
| B5 telemetry: a 200 prints the body and sends the perimeter header with a 10 s timeout | 4 | 2 | 2 |
| Total (counted from the rows) | 24 | 18 | 6 |

Survivors (6): 1 equivalent, 5 real LOW pin gaps.
- Equivalent (read, HIGH): `if show is not None and show != ""` instead of `if show:`.
- F-O-pr597-1 MEDIUM-LOW (2 mutants): the perimeter header is not pinned: removing `headers=auth_headers()` and replacing it with `headers={}` both pass; a gateway with a shared secret would then answer 401 and the CLI would say "gateway answered 401", so the loss shows only against a secured gateway (cli.py telemetry).
- F-O-pr597-2 LOW: the error message can repeat the caller's preset name (`{show!r}`) with no test failing: "repeats nothing the caller sent" is the design (objection 1) and is unpinned.
- F-O-pr597-3 LOW: the order of the listed presets is unpinned (`sorted(PRESETS)` passes).
- F-O-pr597-4 LOW: a 204 (no content) treated as success passes; only 200 is pinned as success.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main; I could not run it. C2 none other.
Optional, NEW PR after the head is frozen: F-O-pr597-1..4 (the header pin first; a test against a secured stub gateway).

Tokens/cost line: not available to me. I do not know.
