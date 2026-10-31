VERDICT: PASS WITH CONDITIONS on 3436007e5071a816f50c8959171ac00e774ef55a

Reviewer Lane 15, cloud-reviewer, C-986, PR 366 at 3436007 (the head of Lane 4's C-841 and my C-799; unchanged: the last commit only made the test canary a made-up marker). UNVERIFIED: no GX10, CI not read. This restates my C-799 and the later C-841; no new probe run today beyond the merge checks.

## Objections first
1. The library fix and the HTTP path differ: the library message for a non-text signer names only the type, but over HTTP FastAPI/pydantic rejects a non-text signer before the PR's guard runs (api.py types the field as text), and the 422 body repeats the submitted value in its validation detail. So the shapes that still echo a value are the HTTP 422s for a list, a dict or a number as signer, and the same default handler repeats a wrong-typed manifest or agent id (C-799, C-841 F-C841-1, probed) (HIGH on those reports; not re-run).
2. Slice 3 is test and library text only for the CLI/library path; it does not change the HTTP echo, so "names only the type" is true of the library message only (HIGH).

## Conditions from C-799 and C-841
- F-C777-1 (the 422 echo over HTTP): OPEN, wider than first written (manifest, agent id too); needs a handler that drops the "input" field or a fixed-text validation response; PR 366 does not claim it.
- F-C777-2 (canary key-shaped): CLOSED (made-up marker).
- README ZWJ/ZWNJ sentence: true (both refused, probed over HTTP, C-841).
- F-C841-1 (guard not on the HTTP path): OPEN, LOW.

## Conflicts with merged PR 364 and PR 388
PR 366 changes 2 files (the signer message and its test, plus the README line, per its diff); merge-tree with main: 0 conflicts; with PR 388 (environment scan tests): 0; PR 364's old head has no relation to these files. No conflict with what is merged or open (HIGH, run).

## Conditions (non-blocking)
1. Open a card for the HTTP validation echo (fixed-text 422s). 2. Keep the README wording honest: library message only.

Not verified: CI, GX10, the echo probes on this run.

CORRECTION: PR 366's diff against main is two files only, the compliance-crosswalk README and tests/test_signer_sanitise_c252.py. It changes no source file. The words "the signer message and its test, plus the README line" and "test and library text only" above are wrong: the library message that names only the type is already on main; this PR pins it with tests and states the ZWJ/ZWNJ refusal in the README. Conclusions about the HTTP 422 echo are unchanged.
