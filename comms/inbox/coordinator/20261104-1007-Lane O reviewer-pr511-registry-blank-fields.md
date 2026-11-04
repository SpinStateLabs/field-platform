# Lane O reviewer: PR 511 (scout S-B6, agent-registry: blank name, owner or domain is a 422; padding stripped) @c42b3488afd83d784058823df869ee3dccd2500c. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head c42b3488. Lane B (registry). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); +23 lines in models.py, +85 in a test file. I did not write the head. Claimed through dispatch.sh (R-PR511-c42b348).

Objections first: (1) "blank" is `str.strip()` only: probe (run, HIGH) on the head: a name of U+200B (zero width space) and one of U+FEFF (byte order mark) are ACCEPTED and stored as-is, while U+2003 (em space) and U+00A0 are handled (U+00A0 padding is stripped, U+2003 alone is refused). The PR's own stated purpose is that an agent with a blank "human owner" (the registry's one hard rule) must not exist; an owner of U+200B is invisible and passes (AgentCreate(owner="​") returned the same string). (2) the PR text says a domain of " finance" would silently miss the kill-switch's exact-match domain halt; the same miss happens for a domain with a trailing zero width space, which this does not strip (read, HIGH). (3) the rule applies at the request boundary only; legacy rows with blank or padded values stay readable (deliberate), so existing bad rows are not cleaned (read, HIGH).

Run here (cloud, scratch worktree on c42b3488, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 46 passed; whole agent-registry suite 357 passed. NOT run: the 16-suite set, CI.

Mutants on agent_registry/models.py (23 run in a scratch worktree; each against the new test file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a blank name, owner or domain is refused on create | 5 | 5 | 0 |
| B2 a blank field is refused on PATCH | 4 | 4 | 0 |
| B3 padding is stripped and stored stripped | 5 | 4 | 1 |
| B4 None (not sent) passes on PATCH | 3 | 3 (all by older tests) | 0 |
| B5 AgentRecord, the read model, is NOT tightened (legacy rows still read) | 3 | 0 | 3 |
| B6 the default domain "general" is unchanged | 3 | 3 | 0 |
| Total (counted from the rows) | 23 | 19 | 4 |
B4 and B5 have 3 mutants each (under the 4 asked).

Survivors (4): 1 equivalent (`return v + ""`), 3 real:
- F-O-pr511-1 MEDIUM-LOW (3 mutants): the stated design decision "AgentRecord is deliberately NOT tightened: a legacy row must still read back" is not pinned by any test. Applying the new validator to AgentRecord's name, owner or domain survives the whole suite, and the PR's own docstring says that would 500 every list over a legacy row (models.py AgentRecord).
- F-O-pr511-2 (probe, not a mutant): zero width and byte order mark names are not blank (objection 1).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 objection 1 named: either strip the invisible characters (a small named set: U+200B, U+200C, U+200D, U+2060, U+FEFF) or record the decision that only str.strip() whitespace counts.
Optional, NEW PR only after the head is frozen: F-O-pr511-1 pin (a legacy row with a blank owner must still list); B4 pin in the new file (explicit null on PATCH).

Tokens/cost line: not available to me. I do not know.
