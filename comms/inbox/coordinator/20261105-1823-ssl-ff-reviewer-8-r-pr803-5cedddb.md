# Review R-PR803-5cedddb — PR 803 (pytest --shard I/N for tools/tests; rebuild of #478)
Head reviewed: 5cedddbd08335f810a9b437d2039b8bf1fe3c218. Head is a fast-forward of main (HIGH).

## VERDICT: PASS

## Checks
1. Identity: 1 commit, author AND committer Don Hagell 13129187+dhagell noreply (HIGH).
2. .github/: no change (HIGH). Files: tools/tests/_sharding.py (+48), conftest.py (+37), test_sharding_c1192.py (+107); no other file (HIGH).
3. Fidelity: `git patch-id --stable` of this commit = 01e22434859e, identical to PR 793's commit (ff613b31) which is also commit 231156a7 inside vehicle #814 (HIGH). The PR body's "byte-identical to #478 head 079e1b7d" I did not re-check.
4. Code read: `parse_spec` strict I/N; `assign` greedy longest-first, deterministic, keyed by file name, weights only steer balance; conftest deselects other shards via `pytest_deselected`, no effect without `--shard`; bad spec is a UsageError before collection (HIGH).
5. Tests on head: test_sharding_c1192 29 passed (HIGH).
6. Mutants, 13 run: 10 killed, 1 equivalent, 2 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| S1 | allow shard 0 (`0 <= I`) | killed |
| S2 | reject I == N (`I < N`) | killed |
| S3 | drop `left.isdigit()` check | equivalent (int() still raises ValueError; only the message differs) |
| S4 | tie-break to HIGHEST shard | SURVIVED (LOW: the "ties go to the lowest shard" statement is not pinned) |
| S5 | sort lightest-first | killed |
| S6 | load never updated | killed |
| S7 | shard numbers 0-based | killed |
| S8 | no dedupe of file names | killed |
| C1 | keep/drop swapped | killed |
| C2 | `pytest_deselected` hook not called | SURVIVED (LOW: "shows as deselected, not skipped" is not asserted; kept/dropped sets are still right) |
| C3 | `items[:] = keep` removed | killed |
| C4 | bad spec no longer a UsageError | killed |
| C5 | no early return without `--shard` | killed (collection errors) |
7. Not verified: whole tools/tests collection under the new conftest (author states 3579 collected, 9 collection errors from missing sibling modules; not re-run), GX10 16/16. Note: the sharding test spawns `python -I -m pytest`, so pytest must be installed in the interpreter's site-packages (author's note, consistent with my run).

## Conditions: none. Head frozen at 5cedddbd. Optional LOWs (S4, C2) in a NEW PR.
Coordination note: the same commit is already in vehicle #814 (batch m4); landing both is a duplicate, not a conflict.
