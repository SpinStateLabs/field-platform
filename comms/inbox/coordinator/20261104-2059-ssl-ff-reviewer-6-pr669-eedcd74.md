# Reviewer report: PR 669 @ eedcd747 (agent-incident-retro unique_labels never gives two inputs one label, S4-21)

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Claim: R-PR669-eedcd74. Head fetched from refs/pull/669/head; one commit on main; 2 files (+76/-3): defence-shield/agent-incident-retro/src/agent_incident_retro/parsers.py and tests/test_unique_labels.py. Author and committer: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).

## Verdict: PASS (head eedcd747). Standing: green CI on the landing head.

## Objections first (FORCE-O)
1. Label assignment depends on input ORDER: a real file `a.log#2` that comes first keeps its name and pushes the generated labels up (measured: the order `a.log#2, a.log, a.log, a.log` gives `['a.log#2', 'a.log', 'a.log#3', 'a.log#4']`), while the reverse order gives `['a.log', 'a.log#2', 'a.log#2#2']`. Both are collision-free; the labels an operator sees for the same files differ by command-line order. Acceptable, and the tests assert uniqueness, not one fixed answer (LOW; HIGH that it is as measured).
2. Case: two names differing only by case are distinct labels (a mutant that folds case, U9, survives). On a case-insensitive filesystem two such paths could be one file; not this PR's claim (LOW, no test).
3. The labels are the evidence-pack and cited-line key, and unique_labels is called from two places (engine.py:36 and cli.py:136) that each recompute it from the same list; they agree only because the function is deterministic. A caller that passes the list in a different order to the second call would mislabel (not found in the code today; MEDIUM, checked by grep: only those two callers).
Steelman: before the change `["a.log", "a.log", "a.log#2"]` produced the label `a.log#2` twice, so two inputs shared one key in the evidence pack and the cited-line check; now a taken candidate is skipped, the first occurrence of each name keeps its name when nothing collides, and the engine-level test proves the labels that reach the input records are unique.

## Runs (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- new file: 11 passed. Whole defence-shield/agent-incident-retro/tests: 240 passed.

## Mutants (parsers.py; kill = the PR's test file; baseline 11 passed)
| id | mutation | result |
|---|---|---|
| U1 | the old per-name counter restored | KILLED |
| U2 | `used.add` removed | KILLED |
| U3 | suffix starts at 3 | KILLED |
| U4 | collision test changed (`or n > 50`) | KILLED |
| U5 | first occurrence also suffixed | KILLED |
| U6 | used set keyed by path not label | KILLED |
| U7 | separator `~` | KILLED |
| U8 | base is the stem not the name | KILLED |
| U9 | collision test case-folded | SURVIVED (objection 2; not the PR's claim) |
| U10 | output list reversed | KILLED |
Total 10; 9 killed, 1 survivor outside the claim; no equivalent mutants identified.
