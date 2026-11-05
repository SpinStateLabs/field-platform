VERDICT: PASS WITH CONDITIONS on 3e13b5235e2ec4b2b16a7ce3137c9f986160a117  (ssl-ff-reviewer-9; Windows, Python 3.14.2, no GX10, CI not read)

R-PR788-3e13b52, PR 788 (S8-29, agent-incident-retro verify: hostile packs are failed checks, unreadable files one line). Applies to this head only.

OBJECTIONS FIRST
1. The PR's own "not covered" claim is wrong on this box: "a hostile pack that makes canonical() ... raise (a JSON-loaded pack cannot)". On Python 3.14.2 (the project's CI matrix includes 3.11 to 3.14, ci.yml line 22) json.loads accepted a pack nested 16000 deep and verify_pack then raised RecursionError inside canonical(): `typer` CliRunner on `verify` with {"signer": [[[...]]]} at depth 16000 gave exit_code 1 with `r.exception` RecursionError and no output (an uncaught traceback), while depth 200000 (loads itself fails) gives the PR's one-line `error: could not read the pack: RecursionError`. So the fix covers the depth range where loads fails but not the window between about 16000 and loads' own limit. I did not test 3.11 to 3.13 (older versions limit loads and dumps alike, I expect, but did not check). HIGH on the 3.14.2 result, LOW on other versions.
2. Mutant V15 (drop the `isinstance(raw, str)` guard in the raw-lines check) SURVIVES: a request whose `raw` is a truthy non-string (an int, a list) is handled by that guard but no test sends one, so removing the guard (a TypeError or AttributeError traceback) would pass all 56 tests. HIGH on the survivor; the code itself is right.
3. A verifier that continues after a shape failure must never end ok: it does not. `ok=all(c.ok ...)` over the checks, every shape problem adds a failed Check, and V18 (pack-shape check recorded as passing) and V3/V6/V7/V19 (shape checks silenced) are all killed. No fail-open path found in the diff. HIGH.
4. Mutant V2 (no explicit "events not a list" check) survives, but it is equivalent: a non-list `events` already raised TypeError inside the existing `except Exception` and became "events parse" before this PR. The new check only names the case. HIGH.
5. Behaviour change to flag: the CLI now reads `--pub` before `--report` and `--sources`; an unreadable pack plus unreadable --pub reports the pack first (as before). Only the order of two possible error lines differs. LOW.
6. Base is 13 commits behind main; `git merge-tree` is clean; the PR is two commits (49ad5caa, 3e13b523) on the one card. HIGH.

ASSUMPTIONS
A1 The test file's 56 cases are the PR's claim; I recounted by running them. A2 I treat the shape handling as security-relevant because the verifier is the tool a third party runs on an untrusted pack.

REASONING / CHECKS
1. Diff read: cli.py +22/-4, evidence.py +66/-11, new test +176; nothing under .github/. `_dicts`, `_is_ref` (bool line refused), `_is_input` helpers; each wrong shape adds a named failed Check; `pack shape` returns at once. build_pack untouched. HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONPATH = head src + field-core src, import path confirmed): new file 56 passed; whole agent-incident-retro suite 283 passed, 2 skipped, 0 failed. The PR body reports 281 passed, 2 skipped, 1 failed (a 0.2 s timing assertion); on this box that timing test passed, so the counts differ by 2 passed and 1 failed. The 2 extra passes are not explained by the diff (the PR was written before its second commit added tests: probably those). HIGH on my numbers.
4. Mutants on a copy of the head, the new file, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| V1 | non-dict pack check removed | KILLED |
| V2 | events-not-list check removed | SURVIVED (equivalent, objection 4) |
| V3 | findings shape never reported | KILLED |
| V4 | _is_ref accepts a bool line | KILLED |
| V5 | _is_ref ignores sha256 type | KILLED |
| V6 | inputs shape never reported | KILLED |
| V7 | bad evidence lines not reported | KILLED |
| V8 | CLI pack: OSError not caught | KILLED |
| V9 | CLI pack: RecursionError not caught | KILLED |
| V10 | CLI prints the exception text, not the class | KILLED |
| V11 | CLI refusal exits 0 | KILLED |
| V12 | CLI --pub unreadable not caught | KILLED |
| V13 | CLI --report unreadable not caught | KILLED |
| V14 | CLI --sources unreadable not caught | KILLED |
| V15 | raw non-string not guarded | SURVIVED (real, objection 2) |
| V16 | non-object signer raises | KILLED |
| V17 | non-object chain raises | KILLED |
| V18 | pack-shape check passes (ok True) | KILLED |
| V19 | non-list requests not reported | KILLED |

Counted from the table: 19 run, 17 KILLED, 2 SURVIVED (1 equivalent, 1 real), 0 NOT APPLIED. Per behaviour: pack-level shapes 5 (V1, V16, V17, V18, V2), findings and request shapes 5 (V3, V4, V5, V19, V15), inputs/evidence shapes 2 (V6, V7), CLI unreadable files 7 (V8-V14), error text and exit code 2 (V10, V11). HIGH on the counts.

CONDITIONS
C1 (required before merge or an explicit ruling) either make the depth window safe (catch RecursionError around the verify call in the CLI and print the same one line, or inside verify_pack as a failed check) with a test at a depth that loads but fails to verify (16000 worked on 3.14.2), or correct the PR's "cannot" sentence and file it as a known gap. A condition fix is the only push allowed on the head.
C2 (non-blocking) add a test with a non-string `raw` so V15 dies.
C3 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me, and note the 3.11 to 3.13 CI jobs should be read for the depth case.

NOT VERIFIED
Python 3.11 to 3.13 behaviour for the depth window, CI, GX10, the two extra passes versus the PR body.

CONCLUSION
The change removes the traceback paths the PR lists and no fail-open path exists: 56 and 283 tests pass, 17 of 19 mutants killed (1 equivalent). But a pack in a narrow depth window still crashes the CLI with an uncaught RecursionError on 3.14.2, which contradicts the PR's own "cannot", and one guard is unpinned. PASS WITH CONDITIONS: C1 needs a fix or a ruling before merge; C2 optional; C3 the gate. Head frozen except a condition fix.
