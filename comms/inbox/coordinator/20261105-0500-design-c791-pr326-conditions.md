VERDICT: C-791 NONE OF THE C-729 CONDITIONS IS CLOSED at da33a9a1541e65010ac6ef53d075040b0b3fdd65 (PR 326): the head is still da33a9a, the commit C-729 reviewed (checked with `git ls-remote`-equivalent fetch of refs/pull/326/head). Nothing changed, so every open item in 20261105-0030-design-c729-pr326-delta-c642.md stays open.

## Conditions and state at this head (file:line from that note)
1. 200 reply with non-JSON or wrong-shape body from the heartbeat: raw JSONDecodeError (`doc` holds the body) or pydantic ValidationError (message embeds a truncated repr of body values), not `HeartbeatUnreachable` (field_agent/liveness.py:69, also `checkin`). OPEN. HIGH (observed).
2. Federation 200 BLOCK: `CrossingBlocked` message carries the broker's `reasons` and `clause_id` unbounded (10,054 characters from a 5,000-character probe), and a non-JSON 200 leaves the body on `__cause__.doc` (field_agent/federation.py:158-168). OPEN. MEDIUM (observed).
3. Transport-error text interpolated: liveness.py:64, usage.py:106 and :138, federation.py:150 and :162. OPEN, a decision. MEDIUM.
4. Sentinel `check` command echoes the reply body: conformance_sentinel/cli.py:48-49 (non-200) and :52. OPEN. LOW-MEDIUM.
5. A governor 404 always reads "no spend cap" (usage.py:110, :141). OPEN, LOW.

## Any raise or log site still carrying a body (the card's question)
Beyond the four above: none found in the three packages by my AST sweep at this head (field-agent, field-core, conformance-sentinel and claude-approver; remaining hits were CLI echoes of exception text and local-file errors). `upstream_error` sites: 17 (clients.py x6, usage.py x4, bootstrap.py x2, federation.py, liveness.py, sentinel cli.py and seeded.py x3). HIGH on the list, MEDIUM on completeness (sweep is AST-based).

## What I did NOT do
- No new probe or mutant run; this note re-reads my C-729 results against an unchanged head.
