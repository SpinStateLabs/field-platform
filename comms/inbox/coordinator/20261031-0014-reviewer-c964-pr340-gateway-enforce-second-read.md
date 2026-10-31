VERDICT: PASS WITH CONDITIONS on 25ffdc11022c6b8ae655fef5d3b4548499aebe3a

Reviewer Lane 15, cloud-reviewer, C-964, PR 340 at 25ffdc1 (head unchanged since my C-910, re-fetched). Independent second read after C-933. UNVERIFIED: no GX10, CI not read; docs read against source at the PR head, no code run.

## Objections first
1. The gateway enforce section is accurate for what it states and silent on a second enforcement stage that exists in the same code: with FORCE_GATEWAY_ENFORCE and FORCE_GATEWAY_TOOL_CHECK both on, every tool_use block in the upstream reply is checked against the sentinel and a refused block is replaced by a refusal text block; when every tool block is stripped, a "tool_use" stop reason becomes "end_turn" (api.py:591-640, docstring :44; flag at :271, :308). INTEGRATION.md:204-218 says "ALLOW ... the example needs more" and never mentions it; a reader enabling enforce would not learn that a reply can be rewritten. LOW-MEDIUM omission, not a false claim (HIGH, read).
2. Also not stated: each 403 and 503 refusal appends a best-effort `gateway.refused` ledger event (api.py:541-547). Omission, LOW (HIGH, read).
3. The citation cluster is not uniformly exact: the 502 citation `api.py:196-202` is off by one at its start (the `if not api_key` test is :197, the raise :198-203); the other cited ranges contain what they name (docstring :41-43 and :24-40, handler :887-910, `_authorize` :551-585, `SentinelClient.check` :358-375 at the PR's own base). The doc already says its cites were read against an older main (HIGH, read; LOW impact).
4. The doc's table row "gateway meters `except: pass`" (best-effort) is a design statement I confirmed only as far as the code showing bare `pass` handlers at api.py:526 and :538; I did not trace which handler it means (not verified).

## Gateway enforce section against code (each claim)
- Requires `x-field-agent-id` and `x-field-token` (the delegation token id); either missing is 401 naming both: handler api.py:887-899 (HIGH).
- Reads `x-field-action`, default `llm.messages`: `action = (x_field_action or "").strip() or EGRESS_ACTION` at api.py:896; the constant is imported from field_core.llm (api.py:72). The literal value is not shown in this file; I did not open field_core.llm (docstring :24-40 says "exactly `llm.messages`") (MEDIUM).
- Asks the sentinel: `SentinelClient.check` api.py:358-375, POST /check with agent id, token id, action (HIGH).
- 403 for BLOCK or ESCALATE with the body fields listed (`decision`, `clause_id`, `reasons`, `agent_id`, `action`, `escalation` on ESCALATE, `retry_after_seconds` when supplied): _authorize api.py:571-586 (HIGH).
- 503 for unreachable, timeout, non-200, a non-JSON body, no verdict, and FIELD_SENTINEL_URL unset: _authorize :556-570 and SentinelClient.check (the first two lines of its body-handling raise SentinelUnavailable for non-JSON and for no verdict) (HIGH).
- "No upstream call in any of them": the enforce block runs before passthrough and any bypass window and returns the refusal before the forward (api.py:887-899) (HIGH).
- Under enforce the `x-force-passthrough: judge` exemption holds only for the three self-manifest ids: `SELF_AGENT_IDS` has exactly three members (conformance-sentinel, the gateway's own self id, compliance-crosswalk) at api.py:269; the exemption is dropped for any other id at :906-908 (HIGH). "Their identity is still checked": the enforce block precedes it (HIGH).

## Public-safety and claims-above-code scan
Estate address, flag value, build SHA, deploy status or credential: none. The only host-shaped strings are the loopback defaults in the environment table (127.0.0.1 with local ports), which are code defaults. Words that could read as deploy state (GB10, a named workstation, fly.dev, "deployed", "armed on"): 0 in the file (HIGH, grep). Nothing in the enforce section claims more than the code enforces; the omissions are above.

## Authorship, overlap
Author and committer: the no-reply Don Hagell identity on every commit. Overlap: per C-910, no conflict with main or the PRs tried.

## Conditions
1. Add one sentence on the tool-check stage and the gateway.refused event, or point at the README section that has them. Non-blocking.
2. Fix the first line of the 502 citation. Non-blocking.

Not verified: CI, GX10, field_core.llm's constant, the "except: pass" row.
