# Lane O reviewer: PR 369 (C-772, field-core authn: per-tier perimeter keys, a read key never authorises a write) @40951fe60f0f3916256d0f6e9c55f2759bd5666b. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 40951fe6. Lane A (field-core, security). 13 commits; 12 carry author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>` and ONE, 40951fe6 (the head itself), carries `Don Hagell <dhagell@users.noreply.github.com>`, the noreply form without the numeric id (git log, HIGH): see C1. The head is 232 commits behind origin/main 97dcfec1; `git merge-tree` onto main is clean (tree 94b4b15c, HIGH). Files: authn.py +112/-3, test_authn_tiers_c772.py +536, one ENVIRONMENT.md row. An earlier reviewer report exists on head f685e089 (Lane 4, C-783, PASS WITH CONDITIONS, filed 20261105-0500); I read its first lines only; this is an independent review of the CURRENT head, which carries 12 more commits (path templates, internal routes, empty capture). I did not write the head. Claimed through dispatch.sh (R-PR369-40951fe).

Objections first: (1) the control rests on the HTTP method: a GET that changes state is read-tier unless the adopter lists it in `write_only_paths`; the module docstring says so itself ("the method is the only thing this layer can see") (read, HIGH). Every service that adopts a read key must audit its GET routes; this PR does not list any adopter's write-GETs. (2) OPTIONS is a safe method here, so a read key answers a CORS preflight on every path (read, HIGH; usually harmless). (3) OVERLAP with PR 490 (field-core authn non-ASCII x-field-auth, my report 20261104-2100, head ddf8b639): both rewrite the full-key comparison in `_field_authn`. This PR's `_same` encodes BOTH sides with UTF-8 (`surrogatepass`); PR 490 encodes the presented string with latin-1 (Starlette decodes header bytes as latin-1) and the secret with UTF-8. For a non-ASCII configured key the two approaches disagree on what the wire bytes are, and the two PRs will conflict textually in authn.py; whichever lands second needs a decision and a test (read, HIGH; I did not merge the two to run it).

Run here (cloud, scratch worktree on 40951fe6, relative PYTHONPATH): test_authn_tiers_c772.py plus test_authn.py: 41 passed; whole packages/field-core suite 1168 passed, 2 skipped. NOT run: the 16-suite set (the 14 services' adoption of the tier keys is the earlier report's subject), CI.

Mutants on authn.py (36 run in a scratch worktree on real code lines; each against the two authn test files, survivors against the whole field-core suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a read key is accepted only on a safe method (GET, HEAD, OPTIONS) | 6 | 6 | 0 |
| B2 a write-only path is refused to a read key: exact, template, trailing slash, root_path, empty capture, both path spellings | 10 | 9 | 1 |
| B3 the two internal operator routes are never in the read tier | 4 | 4 | 0 |
| B4 a read key equal to the full key is refused at install (and neutralised at run time) | 4 | 3 | 1 |
| B5 with a read key and no full key a write is refused, never open | 3 | 2 | 1 |
| B6 a service-specific read key replaces the generic one | 3 | 3 | 0 |
| B7 comparisons are constant-time over bytes | 2 | 1 | 1 |
| B8 read_auth_headers returns the read key only | 4 | 4 | 0 |
| Total (counted from the rows) | 36 | 32 | 4 |
B5 and B7 have 3 and 2 mutants (under the 4 asked: few distinct wrong values).

Survivors (4): 2 equivalent or untestable, 2 real:
- Equivalent (read, MEDIUM): removing the run-time neutralisation of a read key equal to the full key (`rkey = None`): an equal key is accepted by the full-key branch anyway; and `presented == secret` instead of `hmac.compare_digest` on the full-key branch: same result, only a timing property, which a behavioural test cannot pin (a mock of hmac would).
- F-O-pr369-1 MEDIUM-LOW: dropping the SECOND path spelling (`request.scope["path"]`; only `request.url.path` is checked) passes the whole field-core suite: no test sends a request whose scope path and URL path differ (authn.py `matches`).
- F-O-pr369-2 MEDIUM-LOW: `hmac.compare_digest(presented, key)` without the byte encoding in `_same` passes: no test sends a non-ASCII value through the read-key or full-key comparison, so a TypeError (a 500, the PR 490 bug) could return unnoticed (authn.py `_same`); this ties to objection 3.

CONDITIONS (blocking): C1 the head commit's identity form: re-author inside the coordinator's batch (patch-id identical) or a coordinator ruling that the unnumbered noreply form is acceptable. C2 CI green and a GX10 16-suite run on the exact head rebased on current main (232 behind), including every service that passes `service=` or `write_only_paths`; I could not run it. C3 a recorded order and one resolution for the PR 369 / PR 490 overlap (objection 3), with a non-ASCII key test on whichever lands second.
Optional, NEW PR after the head is frozen: F-O-pr369-1 and -2 pins.

Tokens/cost line: not available to me. I do not know.
