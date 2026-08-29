# field-agent integration knowledge (deep reference)

Distilled from `docs/INTEGRATION.md` and `packages/field-agent/README.md`
at field-platform commit `4df1cfc`. When working inside the monorepo,
prefer those files — they are the source of truth.

## Environment

| Env var | Default | Used for |
|---|---|---|
| `FIELD_SENTINEL_URL` | `http://127.0.0.1:8004` | hook 1 (actions) |
| `FIELD_GOVERNOR_URL` | `http://127.0.0.1:8006` | hook 2 (usage/spend) |
| `FIELD_KILLSWITCH_URL` | `http://127.0.0.1:8005` | hook 3 (liveness) |
| `FIELD_REGISTRY_URL` / `FIELD_DELEGATION_URL` | `:8001` / `:8003` | `bootstrap` only |
| `FIELD_SHARED_SECRET` | *(unset)* | when set, every SDK call carries `x-field-auth` (read per request — a secret exported later is honored) |
| `FIELD_SENTINEL_MODE` | `log_only` | SERVED sentinel default; log_only answers ALLOW and shadow-ledgers the true verdict — set `enforce` for real BLOCKs |

Full port map: registry :8001, ledger :8002, delegation :8003, sentinel
:8004, kill-switch :8005, governor :8006, ops-console :8011. Every service
serves interactive OpenAPI at `http://127.0.0.1:<port>/docs`.

## Operator setup (a human does this BEFORE the agent runs)

```bash
field validate manifests/my-agent.yaml
governor set-cap my-agent --from-manifest manifests/my-agent.yaml
governor set-policy my-agent --allowed-model claude-haiku-4-5 --token-rate-limit 200000
fieldagent mint my-agent --granted-by "Controller, Finance" \
  --scope "read timesheets" --scope "draft invoices" --ttl-seconds 3600
```

Or in Python (operator-side script, NOT agent code):

```python
from field_agent import bootstrap
bootstrap.register("my-agent", name="…", owner="…", domain="finance",
                   manifest_ref="/abs/path/my-agent.yaml")
token = bootstrap.mint("my-agent", granted_by="Controller, Finance",
                       scope=["draft invoices"], ttl_seconds=3600)
```

The agent then carries `token.token_id` — an opaque uuid; authority lives
server-side. `FieldAgent(token_id=...)` also accepts a zero-arg callable
for rotating tokens. See `templates/bootstrap_operator.py` for the full
sequence including the raw-REST cap/policy PUTs.

## Hook 1 — ACTIONS

```python
@agent.governed("draft invoices")     # or: verdict = agent.check("draft invoices")
def draft(row): ...
```

- ALLOW ⇒ the callable runs; `check()` returns the verdict dict
  (`decision`, `clause_id`, `reasons`, …).
- BLOCK ⇒ `ActionBlocked` (`.verdict` has `clause_id`, `reasons`).
- ESCALATE ⇒ `ActionEscalated` — the human queue already has the item.
- **Sentinel unreachable ⇒ `ActionBlocked`** (fail-closed; this is the
  sentinel's own client `conformance_sentinel.governed`, re-exported
  unchanged and identity-tested).
- `irreversible=True` marks the call for the manifest's
  irreversible-action policy; `context={...}` passes through to the verdict.
- The sentinel's 8-step check includes scope = token ∩ manifest — the
  narrower grant wins, so an action string must appear in BOTH.

## Hook 2 — USAGE

```python
report = agent.report_usage("claude-haiku-4-5", input_tokens=42_000,
                            output_tokens=9_000, note="draft INV-001")
report = agent.report_usage_from(anthropic_response)   # via extract_usage()
status = agent.report_spend(cents=12_000, actions=1)   # non-LLM operating cost
```

FIELD prices tokens from the dated price book (exact integer units, 1e-7
USD), folds cost into the SAME cap as dollar spend, and returns `rogue`
findings: `rogue_model` (off allow-list), `rogue_burst` (past rate
ceiling), `unpriced` (unpriceable ⇒ itself a signal). Each finding is an
escalation and a ledger event.

**Strict by design:** a failed report raises (`UsageReportError`; governor
404 no-cap raises `NoSpendCapError`). A best-effort reporter would produce
an agent that believes it is metered while spending unmetered.

**Observed alternative** (removes trust in self-reported counts): route
LLM calls through force-gateway; metering happens at the proxy.

```python
httpx.post(f"{GATEWAY}/v1/messages", json=payload,
           headers={"x-field-agent-id": "my-agent", "x-force-preset": "analysis"})
```

| | self-reported (`report_usage`) | observed (force-gateway) |
|---|---|---|
| trust | agent's honesty | gateway sees the real response |
| coverage | any provider/client | calls routed through the gateway |
| failure mode | strict — raises | best-effort — gateway meters |
| extra hop | none | one proxy |

## Hook 3 — LIVENESS

```python
agent.ensure_alive()          # raises AgentKilled unless status is active
hb = agent.heartbeat()        # observer form: returns killed=True, never raises on it
```

- Unknown agent ⇒ kill-switch answers `killed=true` ⇒ halt (fail-closed).
- Kill-switch unreachable / non-200 ⇒ `HeartbeatUnreachable`, which
  **subclasses `AgentKilled`** — `except AgentKilled: halt()` cannot fail
  open on an outage.
- `heartbeat_max_age=30.0` makes every `check()` lazily re-verify liveness
  when the last confirmation is older than 30 s.
- Latency honesty: the halt happens at the NEXT `check()`/`ensure_alive()`
  — there is no background thread (a thread can set a flag, not stop
  code). Platform backstop: a killed agent's next sentinel check is BLOCK
  regardless.

## CLI

```
fieldagent version
fieldagent heartbeat AGENT_ID                       # exit 1 killed/unknown/unreachable
fieldagent check AGENT_ID "action" --token-id T     # exit 0 ALLOW / 1 BLOCK / 2 ESCALATE
fieldagent report-usage AGENT_ID --model M --input-tokens N --output-tokens N   # exit 3 on rogue findings
fieldagent mint AGENT_ID --granted-by HUMAN --scope "read timesheets" --ttl-seconds 3600
```

## Troubleshooting

- **`NoSpendCapError` / 404 on usage** — governor refuses to meter
  ungoverned spend: `governor set-cap <agent> --from-manifest <manifest>`.
- **401 mentioning `x-field-auth`** — secret estate + a client without the
  header. The SDK attaches it automatically; hand-rolled httpx/curl must
  add `field_core.authn.auth_headers()`.
- **Everything ALLOWs that shouldn't** — served sentinel defaults to
  `log_only`; look for `conformance.shadow_block` ledger events; set
  `FIELD_SENTINEL_MODE=enforce` where real blocks are wanted.
- **`AgentKilled` for an agent never killed** — unknown to the registry
  (fail closed). Register it, or check the `agent_id` spelling.
- **`E.spend_cap` ESCALATE on every check** — manifest declares a spend cap
  but the governor has none configured; set the cap.

## Worked example

`integration/demo/agent/invoicing_agent.py` runs entirely on the SDK:
`ensure_alive` gate → governed timesheet read → per-row governed drafts
with `report_spend` + `report_usage` (5th draft arrives at 96% of cap and
ESCALATEs) → `transfer funds` BLOCK (`D.scope`) → Opus off the Haiku
allow-list flagged `rogue_model` → after a real kill, the re-invoked agent
halts before any work. Committed run log:
`docs/capstone-evidence/field-agent-run.log`.
