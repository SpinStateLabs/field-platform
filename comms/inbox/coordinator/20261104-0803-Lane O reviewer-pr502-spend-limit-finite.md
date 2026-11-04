# Lane O reviewer: PR 502 (S-A4, field-core SpendCap.limit and DelegationToken.max_spend_usd refuse Infinity) @69e2f97a24c43455c85f17e38b0be7dc34d7d303. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 69e2f97a. Lane A (field-core). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH). I did not write the head. Claimed through dispatch.sh (R-PR502-69e2f97).

Objections first: (1) the fix is at the model that RECEIVES the value; the DOA roster row that SUPPLIES it still accepts infinity: services/delegation-authority/src/delegation_authority/doa.py:60 `max_spend_usd: float | None = Field(default=None, ge=0)`. Probe (run, HIGH): a roster row with max_spend_usd inf or 1e999 and a rostered mint: on main the mint is refused with 502 "ledger unreachable... Out of range float values are not JSON compliant"; on this head DelegationToken(...) at api.py:337 raises an UNHANDLED ValidationError (a 500 in production; TestClient re-raises). Both fail closed (no token minted), but the status and message get worse and the root cause (roster accepts inf) is not fixed. (2) the model constraint has no schema counterpart (JSON schema cannot express infinity; builder says unchanged), so a YAML `.inf` manifest path is covered only through from_dict, as the builder states. (3) the 1e300 finite value is still a cap that never trips in practice; out of scope.

Run here (cloud, packages/field-core, relative PYTHONPATH): new file 20 passed; whole field-core suite 1564 passed, 2 skipped, matching the builder. NOT run: the 16-suite set, delegation-authority and conformance-sentinel suites (the builder reports 257 and 263 passed), CI.

Mutants (22 run, scratch worktree on the exact head; each against the new file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 SpendCap refuses inf, -inf, nan (flag dropped, flag true, upper bound 1e300, no-op) | 4 | 3 | 1 |
| B2 SpendCap keeps finite positive limits | 4 | 4 | 0 |
| B3 SpendCap still refuses 0 and negatives | 4 | 4 | 0 |
| B4 manifest with a non-finite cap is refused | 2 | 1 | 1 |
| B5 token refuses non-finite max_spend_usd | 4 | 3 | 1 |
| B6 token keeps None, 0 and finite | 4 | 4 | 0 |
| Total (counted from the rows) | 22 | 19 | 3 |
B4 is under-sampled (2 of 4): the manifest path runs through the same SpendCap field, so there is one real mutant; the second was a no-op of mine and is non-informative.

Survivors (3, none a pin gap): 2 are EQUIVALENT alternatives (an upper bound of 1e300 also refuses inf and nan and keeps every tested finite value: B1 and B5); 1 is my no-op mutant (B4). Equivalence argued by read, MEDIUM.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 objection 1 named: either add allow_inf_nan=False to doa.py:60 in this PR with a mint test (expect 422/503, not 500), or record a follow-up card before this merges, because this PR alone turns a 502 into an unhandled 500 on that input.
Optional, NEW PR only after the head is frozen: a roster-level test for inf and 1e999.

Tokens/cost line: not available to me. I do not know.
