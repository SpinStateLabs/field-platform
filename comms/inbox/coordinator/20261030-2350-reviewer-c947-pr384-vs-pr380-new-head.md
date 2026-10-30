VERDICT: PASS WITH CONDITIONS on ca4154579040a7f0c55527dd5d3fd3a9824c345c (PR 384) and PASS WITH CONDITIONS on e17ea8658bdcbf4dc2ca6ae1c0b3062ec2a7d7bd (PR 380); my C-898 supersession conclusion is REVERSED

Reviewer Lane 15, cloud-reviewer, C-947. UNVERIFIED: no GX10, CI not read; scratch trees, loopback stubs only. Replaces the supersession finding in my C-898 (written against PR 380's older head 7551327).

## Objections first
1. C-898 said PR 384 supersedes PR 380 because 380 lacked the attest tool and had seven tools against a design note of eight. That premise is stale. The design note (comms/inbox/coordinator/20261030-1700-design-force-field-mcp.md, "RULINGS, part 3", item 1) records Don's ruling: `POST /agents/{id}/attest` is Tier 3, never in this server, a written exclusion; item 3 says "Tier 2 = 7 tools; total 56; PR #380". PR 380's new head e17ea86 implements exactly that (commit "attest ruled Tier 3 (excluded, written reason), write rate 10 recorded as Don's ruling"; 5 files; catalog `_T3 ... ruled Tier 3 by Don`). PR 384 (ca41545) still ships attest as a Tier 2 write tool (catalog.py:107, "attest_agent"): 8 write tools, 57 total. On the recorded ruling PR 384 is the one out of line (HIGH, read and run: PR 380 at its head, `TOOLS_TIER2` 7, 56 tools in the write process; PR 384: 8 and 57).
2. The coordinator's cards are inconsistent with that record: C-941 and C-902 say "the attest ruling still owed by Don". The design note says it was given (part 3). Either the note part 3 postdates those cards or the cards are stale; I cannot tell which from the repository alone. Don should confirm before either PR merges (HIGH on the contradiction, not verified which is right).
3. Neither PR contains the other. Both branch from PR 368's head 1f7f61f: PR 380 has 3 commits on top of it, PR 384 has 7 (including a main merge for upstream_error). Only one can merge. merge-tree of the two heads was not run; the shared base means conflicts in tools.py, config.py, catalog.py and the tests are certain (not verified by running).
4. "Which is better code" and "which matches the ruling" now point different ways: PR 384 closes more of the C-869 findings (below) but breaks the attest ruling; PR 380 matches the ruling but carries the older findings. The cheapest consistent outcome is to take PR 384 and remove the attest tool plus its test counts, or to take PR 380 and port PR 384's fixes. That is a decision for Don and the coordinator, not me.

## Which supersedes which (answer)
Neither, on the present record. If the part-3 ruling stands, PR 380 matches it today and PR 384 needs a change before it can be the candidate; if Don prefers attest as Tier 2, PR 384 is the only one with it and PR 380's new head would be wrong. Merge only one, PR 368 first.

## Diff between the two (services/field-mcp)
16 files, +1020/-588. PR 384 deletes audit.py (logic folded into tools.py), replaces tests/test_tier2.py (208 lines) with tests/test_write_tier.py (507 lines), and changes client.py, config.py, server.py, catalog.py and the snapshot. PR 380 at e17ea86 differs from its earlier head only in catalog.py, config.py, README, ENVIRONMENT.md and test_route_coverage.py (so C-869's findings on audit.py, client.py and tools.py carry unchanged).

## C-869 F-1 to F-3 against each head
| finding | PR 380 (e17ea86) | PR 384 (ca41545) |
| F-C869-1: ledger requiring caller signatures refuses every write | applies (audit.py unchanged since 7551327) | applies, pinned by a test against the real ledger (test_write_tier.py:489-492); fails closed |
| F-C869-2: timeout after the service acted reads as failure; a retry acts twice | applies, plus outcome rows that state the failure | applies (probed: two calls, two intent rows, two target requests, "unreachable" both times); no outcome rows |
| F-C869-3: operator pair on every Tier 2 call, including routes that never check it | applies | applies (probed: header on a sentinel check call) |
My C-903 report has the 384 probes. For 380 I relied on C-869 plus the diff (no code of the three files changed after 7551327); I did not re-probe 380 (not verified by me).
Other C-869 findings: PR 384 fixed F-C869-5 (intent agent_id must fullmatch the segment pattern) and F-C869-8 (a lock on the limiter); PR 380 did not (per C-869 and the unchanged files).

## Tool count against the design note
Design note original table: 8 (W1). Rulings part 3 (later): 7, total 56. PR 380 = 7 / 56 (probed: `TOOLS_TIER2` 7, write process lists 56). PR 384 = 8 / 57 (C-898 probe, catalog read again here).

## Evidence
- PR 380 at e17ea86: 123 field-mcp tests pass on a scratch tree with service sources on the path.
- PR 384 at ca41545: 229 tests pass (C-903).
- Authors and committers: the no-reply Don Hagell identity on both; no address, flag value or secret in the changed lines I read.

## Conditions
1. Don confirms attest Tier 2 or Tier 3 (objection 2). Blocking for choosing a candidate.
2. Whichever candidate wins carries C-902 (F-C869-1 to -3) as the build card.
3. Close the other PR; do not merge both.

Not verified: GX10, CI, a merge simulation of the two heads, 380's behaviour under probes.
