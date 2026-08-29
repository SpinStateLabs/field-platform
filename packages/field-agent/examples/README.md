# field-agent examples

A copy-paste agent template plus one runnable sample per SDK feature.
Everything targets a live local stack; `run_all.sh` boots one, runs the
full set, and tears it down:

```bash
bash packages/field-agent/examples/run_all.sh
```

| File | Shows |
|---|---|
| `agent_template.py` | **Start here.** The skeleton for a new governed agent: liveness gate → `@governed` work loop → strict metering, with every exception handled the honest way. |
| `04_bootstrap_operator.py` | Operator setup a human runs first: manifest → register → cap → policy → mint. Cap/policy are raw REST PUTs on purpose (see below). |
| `01_actions.py` | Hook 1 — ALLOW returns the verdict, BLOCK/ESCALATE raise before the body runs, `irreversible`/`context` flags. |
| `02_usage.py` | Hook 2 — priced usage, `extract_usage`/`report_usage_from` from an Anthropic-shaped response, `report_spend`, a rogue-model finding, the no-cap refusal. |
| `03_liveness.py` | Hook 3 — `heartbeat` vs `ensure_alive`, a real kill ⇒ `AgentKilled`, unknown-agent fail-closed, revive. |
| `05_rest_api.sh` | **No SDK at all** — the same three hooks via `curl`, for agents in any language. |

Individual samples run after `04_bootstrap_operator.py` (which prints the
token id last): `python 01_actions.py <token_id>`, etc. In an estate with
`FIELD_SHARED_SECRET` set, the SDK samples work unchanged; the REST sample
shows the `x-field-auth` header to add.

## Is there a REST API? Yes — it's the whole interface

The SDK has no private channel; it is a convenience client over the
services' HTTP APIs, so any language can integrate:

| Hook | Endpoint | Service |
|---|---|---|
| ACTIONS | `POST /check` | conformance-sentinel :8004 |
| USAGE | `POST /usage`, `POST /spend` | spend-governor :8006 |
| LIVENESS | `GET /heartbeat/{agent_id}` | kill-switch :8005 |
| register / mint | `POST /agents` · `POST /tokens` | registry :8001 · delegation :8003 |
| operator cap / policy | `PUT /caps/{id}` · `PUT /policies/{id}` | spend-governor :8006 |

Every service serves interactive OpenAPI docs at
`http://127.0.0.1:<port>/docs` (and `/openapi.json`) while running. What a
non-SDK client must re-implement itself: the fail-closed discipline —
treat an unreachable sentinel as BLOCK, an unreachable kill-switch as
killed, and a failed usage POST as unmetered spend. The SDK exists so
Python agents get that discipline for free.
