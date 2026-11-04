# Lane O reviewer: PR 478 (C-1192, pytest --shard I/N for tools/tests) @079e1b7de0393ec86fcfb7bfbb12ec1a532b3b42. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 079e1b7d. Lane A (tools). Four commits on main cd3b7690 (contains main: yes): the feature commit fb07bc29 and three merges of main; all Don Hagell noreply as author and committer (HIGH). Net diff: tools/tests/_sharding.py (+48), conftest.py (+37), test_sharding_c1192.py (+107). I did not write the head. Claimed through dispatch.sh (R-PR478-079e1b7). The coordinator log says an earlier head of this PR was carried through batches; this report is on the current PR head only.

Objections first: (1) the split is computed from the files each process COLLECTS (conftest.py `assign([item.path.name for item in items], total)`), so it is a partition only while every shard collects the same files. Probe (run, HIGH): with one heavy file removed from the collection, 13 of 64 test files change shard (assign(full) vs assign(without test_topology_lint.py) at 3 shards). A runner that passes `-k`, `--ignore` or `--deselect` differently per shard, or a collection error in one shard, would run files twice or never; the docstring says "on the same collection" but nothing enforces it. (2) the weights are one profile of one GX10 run on main 05942b98 (stated in the file); a stale weight only unbalances, never loses a file (read, HIGH). (3) the shards are balanced by seconds, not by tests: measured collect counts per shard on this head, 3 shards: 1032, 793, 2006, total 3831 = full collection 3831 (counted, HIGH).

Run here (cloud, tools/tests, `-p no:cacheprovider`): the new file 29 passed (about 2 s). NOT run: the full tools suite or the 16-suite set (this PR changes no behaviour without the option), CI. Six tools test modules fail to collect in my environment (missing dependencies, same with and without the option), so the collect counts above use --continue-on-collection-errors.

Mutants (36 run, scratch worktree on the exact head, each against the new file; no syntax-broken kills; only the new file references _sharding, so survivors were not re-run against other suites):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 every file in exactly one shard | 5 | 5 | 0 |
| B2 deterministic and order independent | 4 | 1 | 3 |
| B3 heaviest shard within 25 percent of even | 4 | 3 | 1 |
| B4 the three heaviest files in three different shards | 4 | 4 | 0 |
| B5 a good spec parses | 4 | 4 | 0 |
| B6 a bad spec is refused | 5 | 2 | 3 |
| B7a hook: option absent runs everything | 2 | 2 | 0 |
| B7b hook: shards run every test exactly once | 4 | 3 | 1 |
| B7c hook: bad spec is a usage error (rc 4) | 3 | 3 | 0 |
| B7d hook: tests show as deselected, not skipped | 1 | 0 | 1 |
| Total (counted from the rows) | 36 | 27 | 9 |
B7a, B7c and B7d are under the 4 asked per behaviour (B7 as one family has 10).

Survivors (9): 4 equivalent or refusal-equivalent: dedupe by dict.fromkeys then sort (same result); three spec mutants that still raise ValueError, with a different message (an int('') error, same refusal). 5 real LOW pin gaps:
- F-O478-1: the documented tie rule "ties go to the lowest shard number" is unpinned (a `-i` tie-break survives).
- F-O478-2 (the one that matters): cross-process determinism is unpinned. A tie-break by hash(name) % 7 survives because the unit tests compare two calls in ONE process; PYTHONHASHSEED makes str hashes differ per process, which would break the partition. The hook tests start separate processes but over three equal-weight files, which hides it.
- F-O478-3: the balance test uses the module's own WEIGHTS and DEFAULT_WEIGHT, so DEFAULT_WEIGHT = 40.0 survives (self-referential).
- F-O478-4: the hook's assign(..., total + 1) survives: the throw-away project has only 3 files, so a 4th shard that no runner starts is never populated; the hook test needs at least total + 1 files to show a lost file.
- F-O478-5: "deselected, not skipped" (the conftest docstring claim) is unpinned; dropping the pytest_deselected call survives.

CONDITIONS (blocking): C1 CI green on the exact head. C2 a GX10 run: this is a tests/CI-tooling PR, so a light run is acceptable but must say "tests only"; I could not run it. C3 objection 1 recorded: the runner that uses --shard (not in this PR) must give every shard the identical collection arguments, or the split must be computed from a fixed file list instead of the collected items.
Optional, NEW PR only after the head is frozen: F-O478-1..5 pins (F-O478-2 first).

Tokens/cost line: not available to me. I do not know.
