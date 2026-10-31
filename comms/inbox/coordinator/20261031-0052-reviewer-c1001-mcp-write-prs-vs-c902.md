VERDICT: PASS WITH CONDITIONS on ca4154579040a7f0c55527dd5d3fd3a9824c345c (PR 384) and PASS WITH CONDITIONS on e17ea8658bdcbf4dc2ca6ae1c0b3062ec2a7d7bd (PR 380); card C-902 is NOT built

Reviewer Lane 15, cloud-reviewer, C-1001. Heads re-fetched (384 ca41545, 380 e17ea86). UNVERIFIED: no GX10, CI not read.

## Objections first
1. Nothing has been built for C-902: the queue line is still OPEN (no claim, no builder report for Lane 16 after C-774), and neither head changed (HIGH).
2. The attest ruling recorded in the design note (Tier 3; Tier 2 = 7 tools) still conflicts with the queue text that says it is owed; PR 380 matches the note, PR 384 does not (C-947).

## What is built and what is not
| item | PR 380 | PR 384 |
|---|---|---|
| F-C869-1 caller-signed intent row, or a README line | not built | not built (test pins that every write is refused when the ledger requires signatures) |
| F-C869-2 transport error after send returns "outcome unknown; do not retry" | not built | not built (probe: "unreachable", retry sends a second request) |
| F-C869-3 operator pair only on POST /agents and POST /export | not built | not built (header seen on a sentinel check) |
| F-C869-5 intent agent_id must fullmatch the segment pattern | not built | built |
| F-C869-8 lock on the rate limiter | not built | built |
| attest as a tool | excluded (Tier 3, ruling) | included (8th tool) |

## Can the write tier merge once PR 368 does?
Not safely yet: both PRs carry F-C869-1 to -3; F-1 fails closed, F-2 and F-3 do not (a retried write may act twice; the operator key reaches services that do not check it). Neither is a data-loss defect, but F-3 sends a credential to services that never verify it. Writes are off by default (FFMCP_ENABLE_WRITES must be exactly 1) and a separate process, so merging does not turn anything on. By my reading it can merge once 368 does, behind the flag, if Don accepts F-2 and F-3 as declared limits and settles attest; the three fixes are the build card C-902.

## Conditions
1. Open C-902 to a builder lane. 2. Don's attest answer. 3. Pick one write PR (C-981 recommendation: 380 as base with 384's fixes ported, unless Don wants attest in Tier 2).

Not verified: GX10, CI, a merged state of 368 with either.
