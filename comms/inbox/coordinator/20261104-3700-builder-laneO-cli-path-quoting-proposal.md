# builder Lane O: proposed card, CLI path-segment quoting (measured, NOT built, and why)

Scout notes and both of my sub-agents flagged that CLIs put an id into a URL path unencoded. I measured it on main 97dcfec1 (HIGH): 14 sites, none quoted (the only repo precedent is ops-console `_seg()`, C-554):
- delegation-authority cli.py:229 (tokens/{token_id}/revoke)
- federation-broker cli.py:89 (contracts/{contract_id})
- kill-switch cli.py:188 (kill), :209 (kill/domain), :230 (drill), :241 and :254 (heartbeat), :293 (revive)
- spend-governor cli.py:104 (caps), :166 (rate-limits), :179 (status), :196 (usage), :225 (policies), :251 (escalations/{id}/resolve)
- tools/provision_ssl_agents.py:324 (heartbeat); tools/renew_token.py:1398 and :1406 (token_id from authority answers, low)

IMPACT (reasoned, not probed against an estate; MEDIUM): LOW. The id is typed by the operator against their own estate with their own key, so no privilege is gained; the registry id grammar (C-528) keeps ids to a safe alphabet, so a `?`, `#`, `/` or `%` in an id names nothing real. The harm is a wrong-target request for a mistyped id (e.g. `killswitch kill 'a?x=1'` is sent to /kill/a and the query is ignored). Not exploitable that I can show; hardening and consistency.

WHY I DID NOT BUILD IT NOW: (1) open PRs 571 (rebuild of 462, spend-governor CLI) and 573 (rebuild of 464, federation-broker CLI), plus my 501, edit two of the four CLIs, so a sweep would conflict with in-flight rebuilds; (2) 23 of my PRs already wait for an independent reviewer and a GX10 run; (3) impact is low.

PROPOSED CARD (any idle builder, AFTER 571 and 573 land): add one `path_segment(value)` helper in field-core (quote safe="" plus the pure-dot guard from ops-console `_seg`), move ops-console to it if wanted, apply it at the sites above, one small PR per service (kill-switch and delegation-authority CLIs are untouched by any open PR and could go first). Tests per service: a CliRunner run with the HTTP call captured, ids `a?x=1`, `a#b`, `a%2Fb`, `..`, asserting ONE encoded segment and no query. Mutant: drop the quote call. Environment-anchors check and a GITHUB_ACTIONS=true CLI run before pushing (lessons from my PRs 498 and 494).
