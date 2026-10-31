VERDICT: PASS on 1ce17e6cf0efba367d1c0f1819edb309d1b4c144

Reviewer Lane 15, cloud-reviewer, C-957, PR 322. The card names head 6ac0f8e; the head is now 1ce17e6 (one new commit, tests and README only). UNVERIFIED: no GX10, CI not read; scratch tree, real spawned processes.

## Objections first
1. The new race test is wall-clock paced: eight workers start each round at a fixed second after a 6-second lead, so a loaded machine that needs more than 6 seconds to start eight interpreters would make workers miss the barrier and the one-winner count could fail or, worse, pass without the processes truly overlapping. Passed three of three runs here (about 21 seconds each). MEDIUM-LOW (flake risk, HIGH on the pacing, MEDIUM on how loaded the CI hosts are).
2. The production code is untouched since 6ac0f8e (diff of services/federation-broker/src: empty); the delta cannot change behaviour. PASS is therefore on the tests and the README claim (HIGH).
3. PR 327 is the same change built twice (my C-595: merge 322, close 327). It still conflicts with PR 322 in five files; unchanged (HIGH, merge-tree).
4. The joiner collision is documented, not removed: names that differ only by a zero-width joiner or non-joiner are one org, a false 409, never a bypass (Don's ruling, round 3; README section and pinned test). Carried decision, not a defect.

## Questions asked
- C-565 conditions (Lane 4, PR 322 at 98dba84): all five were reported closed by C-578 on f6a9bbe, and nothing in 98dba84 to 1ce17e6 reverses them by my diff of the production file (only the later normaliser lists and the joiner documentation). Re-run: 188 tests pass in services/federation-broker (HIGH, run).
- C-578 PASS head f6a9bbe versus now: four commits later (935a8d0, 5ff3df4, 6ac0f8e, 1ce17e6). The first two widen the dropped invisible-character list and state it is a chosen subset; 6ac0f8e documents the joiner collision; 1ce17e6 adds the process race test and corrects the README (HIGH, git log).
- Is the race still proven? Yes, and now by real processes (C-864 F-C864-1 closed): the new test spawns eight interpreters on one sqlite file per round with differently spelled names of one org; exactly one 'ok' and seven 'conflict' per round, no lock error, five rounds, on a clean database and on a legacy database whose unique index is skipped (HIGH, run). Lane 10's correction (threads only) no longer applies to the head.
- C-864 F-C864-2 (README said the transaction prevents duplicates; it is the index): CLOSED. README now says the partial unique index prevents the duplicate active row and BEGIN IMMEDIATE makes the loser a clean 409 instead of a lock error; pinned by a README wording test (HIGH, read).

## Mutants on the delta (2 applied, 2 killed)
- Removing the BEGIN IMMEDIATE line: the spawned test fails (1 of 2 parameters) (HIGH, run). Removing the unique-index creation: fails (1 of 2 parameters). Each parameter covers one protection, as the test says: the clean database needs the index, the legacy database needs the transaction. Production file restored; worktree removed.

## Evidence
- Author and committer: the no-reply Don Hagell identity on all six commits (read). The delta adds no address, flag value, build id or credential (sweep of added lines: only decorator characters matched).
- merge-tree: no conflict with main or PRs 349, 375, 381, 383, 388.

## Conditions
1. Consider a retry or a larger lead for the barrier if CI hosts are slow (non-blocking).
2. Close PR 327 when 322 merges (carried).

Not verified: CI, GX10, the demo script.
