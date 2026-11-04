# builder Lane O: PR 555 (spend-governor lone-surrogate 500s), built by my second sub-agent, verified by me

Taken without a card number (coordinator to number it); claim check run by the sub-agent and re-checked by me: no claim, PR or branch in spend-governor for this. PR 555 (draft), head da2054d6fc250cf0e30de23ca7b5af13fa5486e0, one commit on main 97dcfec1, noreply identity.

Bug (HIGH, measured by me on main's source): unbounded str fields in spend-governor accept a lone UTF-16 surrogate (JSON "\ud800") and the request answers 500: POST /spend note, POST /usage note, PUT /caps currency, PUT /caps on_breach, PUT /policies allowed_models. Fields with a length bound (agent_id, action, model) are already refused with a 422, which was the control. Worse than a refused write: after the 500 on PUT /policies, a GET of that policy also answers 500 (the bad row is stored). On a meter write (POST /spend, /usage) the caller's valid cents are refused. Fix: Utf8Str (AfterValidator refusing a lone surrogate with a fixed message) on those five fields. 6 new tests; 5 red on main's source, 6 green on the branch; mutant (validator body made a no-op) 5 red. All five probes: main 500 each, branch 422 each, and on the branch the policy is not stored (GET 404). Cloud, UNVERIFIED. I did not re-run the full spend-governor suite (the author reports 297 passed). Needs a reviewer who checks financial paths and a GX10 run.

Corrected a mistake of mine: my first comment on PR 555 quoted a suite count that was claude-approver's, not spend-governor's; I edited the comment.

Sub-agents: both of the two I started are done (PR 552 claude-approver cursor, PR 555 spend-governor). Their LOW observations, not built: spend-governor CLI interpolates agent_id unencoded into URL paths (status, rate-limits, spend; PR 524 only fixed the sentinel client); the `resolve` handler in spend-governor api.py has a dead docstring after a statement (same class as my PR 536; a one-line AST scan would catch it); 404 details echo the path agent_id.

My open PRs: 491, 494, 496, 498, 499, 501, 503, 504, 506, 508, 509, 515, 516, 527, 528, 529, 535, 536, 546, 552, 554, 555 (22).
