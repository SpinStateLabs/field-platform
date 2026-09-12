# Non-Python agents — the raw REST path

The SDK has no private channel; it is a convenience client over the
services' HTTP APIs. Any language can integrate. Runnable curl version:
`${CLAUDE_PLUGIN_ROOT}/templates/rest_api.sh`.

| Hook | Endpoint | Service |
|---|---|---|
| ACTIONS | `POST /check` | conformance-sentinel :8004 |
| USAGE | `POST /usage`, `POST /spend` | spend-governor :8006 |
| LIVENESS (poll) | `GET /heartbeat/{agent_id}` | kill-switch :8005 |
| LIVENESS (check-in) | `POST /heartbeat/{agent_id}` — same verdict, records `last_seen` | kill-switch :8005 |
| register / mint (operator) | `POST /agents` · `POST /tokens` | registry :8001 · delegation :8003 |
| operator cap / policy | `PUT /caps/{id}` · `PUT /policies/{id}` | spend-governor :8006 |

Every service serves interactive OpenAPI docs at
`http://127.0.0.1:<port>/docs` (and `/openapi.json`) while running.

## Request shapes

```bash
# hook 1: ACTIONS — HTTP 200 either way; the verdict body decides
curl -sf -X POST "$SENTINEL/check" -H 'content-type: application/json' \
  -d '{"agent_id":"my-agent","action":"draft invoices","token_id":"'$TOKEN'"}'

# hook 2: USAGE — 201 metered; 404 = no cap = REFUSED (treat as stop)
curl -sf -X POST "$GOVERNOR/usage" -H 'content-type: application/json' \
  -d '{"agent_id":"my-agent","model":"claude-haiku-4-5","input_tokens":1000,"output_tokens":200,"note":"…"}'

# hook 3: LIVENESS — killed=true means STOP
curl -sf "$KILLSWITCH/heartbeat/my-agent"
```

When `FIELD_SHARED_SECRET` is set on the estate, add
`-H "x-field-auth: $FIELD_SHARED_SECRET"` to every call.

## What a non-SDK client MUST re-implement itself

The fail-closed discipline — this is the whole point, and skipping it makes
the client non-compliant:

1. Unreachable sentinel (or any non-200 on `/check`) ⇒ treat as **BLOCK**.
2. Unreachable kill-switch (or non-200 heartbeat) ⇒ treat as **killed**.
3. Failed usage POST (incl. the no-cap 404) ⇒ the spend is **unmetered** —
   stop or retry visibly, never continue silently.
4. `killed=true` for an UNKNOWN agent id is the correct server answer —
   halt, don't "assume fine".
5. ESCALATE is not a retry-until-ALLOW loop — a human has the item.

The SDK exists so Python agents get that discipline for free; in any other
language, port these five rules and say so in the agent's
Enforced-vs-Declared table.
