# Reviewer (lane B, compliance-crosswalk): PR 512 (scout S-B5) collect_evidence encodes the agent id and tolerates odd replies

**Verdict: PASS WITH CONDITIONS on head `756e5c4f7dfacddc6379e8620e5aaecd0d4be590`.** Head unchanged at start and end; base current main (2 files, the diff is the PR's own); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `compliance_crosswalk/api.py` `collect_evidence` (+21/-6): `aid = quote(agent_id, safe="")` used in the events, tokens and caps URLs; the events reply is used only if a list, counting dict entries with a str `event_type`; `tokens` kept only as a list of dicts; `verify` and `caps` only if dicts; else `None` (not collected). New `test_collect_evidence_sb5.py` (29 tests).

## Objections first
1. An empty `agent_id` still builds `?agent_id=` (no filter) on the ledger and delegation reads; the same class as PR 496 (an empty filter listing everything). Not touched or claimed here (MEDIUM, not run).
2. `registry_record` is untouched and still takes whatever `RegistryClient` returns; the PR scopes itself to the other four reads.
3. "Not collected" on a wrong shape turns an attack on the service into a quietly thinner pack: the CLI pack will report fewer sources rather than fail. The author says an unreachable service already behaved that way.

## Measured (GX10 ~/ff-work/wt-ln512, relative PYTHONPATH incl. sibling service src, own venv, python -B)
New file 29 passed; crosswalk suite 398 passed, 5 skipped. CI at read: see Conditions. 16-suite not run by me.

## Mutants (37 rows on api.py; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| Q1 the id is one encoded segment (`safe=""`) | 5 | 0 |
| Q2 the encoded id is used in the events URL | 4 | 0 |
| Q3 the encoded id is used in the tokens URL | 4 | 0 |
| Q4 the encoded id is used in the caps URL | 4 | 0 |
| E1 the events reply: a list of dicts with a str `event_type` only | 6 | 0 |
| T1 tokens kept only as a list of dicts | 3 | 2 (gaps: `all(...)` can become `any(...)` or `True`; no test hands tokens as a list that holds a non-object) |
| V1 verify and caps kept only if dicts | 5 | 0 |
| N1 no events means not collected | 4 | 0 |
Totals counted from the table: killed 5+4+4+4+6+3+5+4 = 35; survived 0+0+0+0+0+2+0+0 = 2; 37 rows. Both survivors are real gaps (T1); every other behaviour has at least 4 kills.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main.

## Findings (non-blocking; new PR only)
- F-512-1 LOW-MEDIUM: add a tokens reply `[ {}, "x" ]` and `[1]` (T1): the guard line `all(isinstance(t, dict) ...)` is the one the PR text promises ("a non-object entry") and no test fails if it is weakened.
- F-512-2 LOW: an empty agent id (objection 1) belongs with the PR 496 empty-filter decision.
