# Builder scout: field_core + field_agent input-shape bugs (card: scout, then build ONE)

RESULT: no build. Honest empty result. No branch, no PR. Main head at scout: origin/main (fetched 2026-11-04). UNVERIFIED (no GX10).

## One real finding, already covered
- field_core/authn.py:56 `hmac.compare_digest(presented, secret)` with a non-ASCII `x-field-auth` value raises TypeError, so an unauthenticated caller gets a 500 (not a 401). Probe on main (fastapi TestClient, secret set, raw header bytes `caf\xe9`): `s3cret` 200, `wrong` 401, `caf\xe9` 500. Fails closed; any network caller reaches it. [HIGH, run]
- Already fixed by open PR 490 (branch fix/authn-non-ascii-header-500). Skipped, not duplicated.

## Checked on main, no defect reachable
- pricing.PriceBook.cost_units: accepts negative token counts (negative cost) but its only caller, spend-governor api.py:503, validates `ge=0` first (api.py:97, usage.py:62). Not reachable. [HIGH, read]
- field_agent usage.UsageClient.report: no client-side check, the governor 422s negatives. field_client.report_usage validates (bool, int, >= 0). Fine. [HIGH, read]
- field_agent canary._drain: bad, negative or oversize Content-Length handled. Fine. [HIGH, read]
- validation._parse_expiry: naive read as UTC. Fine; `now` param naive would TypeError but only tests pass it. [MEDIUM]
- alerts.send: NaN timeout clamps to 0.05. Fine. [MEDIUM, read]
- http_errors, hosts, llm headers, signing verify paths: catch TypeError/ValueError. Fine. [MEDIUM, read]
- Left alone as covered by the named open PRs: ledger.py, manifest.py/SpendCap (incl. an infinite max_spend_usd on delegation.py:38, which pydantic ge=0 admits; reachability unprobed), delegation token datetimes.

## Not verified
operator_auth.py (1659 lines), operator_health.py, rotation_events.py, clients.py body paths, field_agent federation/agent.py were not read in depth. No tests run; no environment_anchors check (nothing pushed).

## Decisions needed
None. Optional: a card for `max_spend_usd=inf` if PR 502 does not cover delegation.py:38.
