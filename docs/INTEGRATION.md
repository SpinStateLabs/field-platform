# INTEGRATION — putting a real agent under FIELD governance

The client SDK is `packages/field-agent`. Three hooks, a few lines each:
actions checked before they run, LLM usage metered, liveness polled with a
fail-closed halt.

## 1. What this gives you — and what it cannot

The SDK is a **client, not an authority**. It adds ZERO new power: every
decision is made server-side by the conformance-sentinel, spend-governor,
and kill-switch. The SDK's only local capability is *refusal* — raising
before ungoverned work runs, raising when metering fails, raising when the
heartbeat says stop.

**The cooperative-perimeter limit, stated plainly: an agent that never
calls the SDK is not governed.** Nothing here injects itself into code
that doesn't opt in. What still applies to a non-cooperating agent is the
server side: a killed agent's next sentinel `/check` is BLOCK, its tokens
can be revoked, and lifecycle-manager finds orphans — but its unguarded
local actions are invisible. Full Enforced-vs-Declared table:
`packages/field-agent/README.md`.

## 2. Five-minute start

```bash
# monorepo (editable, --no-deps: conformance-sentinel isn't on PyPI)
pip install --no-deps -e packages/field-agent
```

| Env var | Default | Used for |
|---|---|---|
| `FIELD_SENTINEL_URL` | `http://127.0.0.1:8004` | hook 1 (actions) |
| `FIELD_GOVERNOR_URL` | `http://127.0.0.1:8006` | hook 2 (usage/spend) |
| `FIELD_KILLSWITCH_URL` | `http://127.0.0.1:8005` | hook 3 (liveness) |
| `FIELD_REGISTRY_URL` / `FIELD_DELEGATION_URL` | `:8001` / `:8003` | `bootstrap` only |
| `FIELD_SHARED_SECRET` | *(unset)* | when set, every SDK call carries `x-field-auth` — read per request, so a secret exported later is honored |
| `FIELD_SENTINEL_MODE` | `log_only` | the SERVED sentinel default; a log-only sentinel returns ALLOW and shadow-ledgers the true outcome — set `enforce` to see real BLOCKs |
| `FIELD_DOA_ROSTER` | *(unset)* | operator-side, read by delegation-authority on every mint: path to the DOA roster YAML. Unset ⇒ mint behaves exactly as before (§3.1) |

```python
from field_agent import FieldAgent, ActionBlocked, ActionEscalated, AgentKilled

agent = FieldAgent("invoicing-agent", token_id=TOKEN, heartbeat_max_age=30.0)

@agent.governed("draft invoices")            # hook 1: ACTIONS
def draft_invoice(row): ...

agent.ensure_alive()                         # hook 3: LIVENESS
resp = client.messages.create(...)
agent.report_usage_from(resp, note="INV-001")  # hook 2: USAGE
```

## 3. Operator setup (before the agent runs)

Governance is configured by a human, not by the agent — which is why these
steps live in CLIs and `field_agent.bootstrap`, and why `bootstrap` is not
re-exported from the package root.

```bash
field validate manifests/my-agent.yaml
governor set-cap my-agent --from-manifest manifests/my-agent.yaml
governor set-policy my-agent --allowed-model claude-haiku-4-5 --token-rate-limit 200000
fieldagent mint my-agent --granted-by "Controller, Finance" \
  --scope "read timesheets" --scope "draft invoices" --ttl-seconds 3600
```

```python
from field_agent import bootstrap
bootstrap.register("my-agent", name="…", owner="…", domain="finance",
                   manifest_ref="/abs/path/my-agent.yaml")
token = bootstrap.mint("my-agent", granted_by="Controller, Finance",
                       scope=["draft invoices"], ttl_seconds=3600)
```

The agent then carries `token.token_id` (an opaque uuid — authority lives
server-side). `FieldAgent(token_id=...)` also accepts a zero-arg callable
for rotating tokens.

### 3.1 Optional — the DOA roster (`FIELD_DOA_ROSTER`)

Who is allowed to be a `granted_by` at all? By default, anyone: the field is
an unchecked string. Set `FIELD_DOA_ROSTER` on **delegation-authority** to a
YAML file and every mint is checked against it first.

```yaml
# copy of manifests/doa-roster.example.yaml
grantors:
  - grantor: Don Hagell, Spin State Labs   # must equal `granted_by` exactly
    allowed_scope:                          # exact FIELD scope strings
      - read timesheets
      - draft invoice document
    max_ttl_days: 30
    max_spend_usd: 500.0   # recorded on the ledger row, NEVER enforced
    active: true           # false retires a grantor without deleting the row
```

```bash
export FIELD_DOA_ROSTER=/data/manifests/doa-roster.yaml   # read per mint, no restart
```

With it set, a mint is refused when: the roster cannot be read (**503**, and
nothing is written to the ledger); the grantor is absent or `active: false`,
the scope is outside that grantor's `allowed_scope`, or the TTL exceeds
`max_ttl_days` (**403**, clause `D.grantor`); the agent has no resolvable
FIELD manifest, or the scope is outside its `manifest.delegation.scope`
(**422**, clause `D.scope`). Refusals carry
`detail: {clause_id, message}`.

Two consequences worth planning for:

- **Register agents with a `manifest_ref`.** Under a roster, an agent whose
  registry record has no resolvable manifest cannot be minted for — that is
  deliberate (fail closed), and it is why `FIELD_DOA_ROSTER` stays unset in
  compose, fly and CI, where the smoke flow registers without one.
- The roster proves that a *string* is on a list. It is not authentication:
  `granted_by` is still unverified. See the delegation-authority README's
  Enforced-vs-Declared table.

Both estates run pre-v1.2 images with the variable unset, so this is Declared
there until Don deploys.

## 4. Hook 1 — ACTIONS

```python
@agent.governed("draft invoices")     # or: agent.check("draft invoices")
def draft(row): ...
```

- ALLOW ⇒ the callable runs; the verdict dict is returned from `check()`.
- BLOCK ⇒ `ActionBlocked` (carries `.verdict` with `clause_id`, `reasons`).
- ESCALATE ⇒ `ActionEscalated` — the human queue has the item; you decide
  how to wait.
- **Sentinel unreachable ⇒ `ActionBlocked`** (clause `E.kill_switch`,
  "failing closed"). This is the sentinel's own client
  (`conformance_sentinel.governed`), re-exported unchanged.
- `irreversible=True` marks the call for the manifest's irreversible-action
  policy; `context={...}` passes through to the verdict.
- A **log_only** sentinel answers ALLOW to everything and shadow-ledgers
  what it would have done — safe-by-default estates behave this way until
  the operator flips `FIELD_SENTINEL_MODE=enforce`.

## 5. Hook 2 — USAGE

```python
report = agent.report_usage("claude-haiku-4-5", input_tokens=42_000,
                            output_tokens=9_000, note="draft INV-001")
report = agent.report_usage_from(anthropic_response)   # same, via extract_usage()
status = agent.report_spend(cents=12_000, actions=1)   # non-LLM operating cost
```

FIELD prices the tokens from the dated price book (exact integer units,
1e-7 USD), folds the cost into the SAME cap as dollar spend, and returns
`rogue` findings: `rogue_model` (off the allow-list), `rogue_burst` (past
the rate ceiling), `unpriced` (no price ⇒ ungovernable ⇒ itself a signal).
Each finding is also an escalation and a ledger event.

**Strict by design:** a failed report *raises* (`UsageReportError`; the
no-cap 404 raises `NoSpendCapError`). A best-effort reporter would produce
an agent that believes it is metered while spending unmetered. If you
truly want fire-and-forget, write the `try/except` yourself — visibly.

**The observed alternative:** self-reported counts trust the reporter.
Route LLM calls through force-gateway instead and metering happens at the
proxy:

```python
httpx.post(f"{GATEWAY}/v1/messages", json=payload,
           headers={"x-field-agent-id": "my-agent", "x-force-preset": "analysis"})
```

| | self-reported (`report_usage`) | observed (force-gateway) |
|---|---|---|
| trust | agent's honesty | gateway sees the real response |
| coverage | any provider/client | calls routed through the gateway |
| failure mode | strict — raises | best-effort — gateway meters `except: pass` |
| extra hop | none | one proxy |

## 6. Hook 3 — LIVENESS

```python
agent.ensure_alive()          # raises AgentKilled unless status is active
hb = agent.heartbeat()        # observer form: returns killed=True, never raises on it
hb = agent.checkin()          # POST: same verdict, and records last_seen
```

- `checkin()` is the only call that writes `last_seen`; an agent that only
  ever polls reads stale on `GET /liveness` forever. Call it on your own
  cadence, and mind the asymmetry with the PowerShell shim: the SDK fails
  **closed** on a pre-v1.2 estate (the POST's 405 raises
  `HeartbeatUnreachable`, which halts), while `field-rest.ps1` deliberately
  does not halt on that 405 and leans on `Get-FieldHeartbeat` instead.
- Unknown agent ⇒ the kill-switch answers `killed=true` ⇒ halt.
- Kill-switch unreachable or non-200 ⇒ `HeartbeatUnreachable`, which
  **subclasses `AgentKilled`** — `except AgentKilled: halt()` cannot fail
  open on an outage.
- `FieldAgent(heartbeat_max_age=30.0)` makes every `check()` lazily
  re-verify liveness when the last confirmation is older than 30s.
- Honesty about latency: the halt happens at the next `check()` /
  `ensure_alive()`, not instantly — there is no background thread (a
  thread can set a flag, not stop code). The platform backstop is that a
  killed agent's next sentinel check is BLOCK regardless.

## 7. Failure semantics

| Exception | Raised when | Do |
|---|---|---|
| `ActionBlocked` | sentinel says BLOCK — or is unreachable | don't do the action; inspect `.verdict` |
| `ActionEscalated` | sentinel says ESCALATE | skip/queue the item; a human has it |
| `AgentKilled` | heartbeat `killed=true` (incl. unknown agent) | halt now; `.heartbeat` has the status |
| `HeartbeatUnreachable` (⊂ `AgentKilled`) | kill-switch unreachable / non-200 | halt now — liveness unknown is not liveness |
| `NoSpendCapError` (⊂ `UsageReportError`) | governor 404: no cap configured | stop; have the operator `governor set-cap` |
| `UsageReportError` | usage/spend report failed to land | the spend is NOT metered — stop or retry visibly |
| `BootstrapError` | register/mint failed | operator problem (409 duplicate, service down) |

## 8. Worked example — the invoicing agent

`integration/demo/agent/invoicing_agent.py` runs entirely on the SDK:
`checkin()` gate (a POST, so the run is visible to `GET /liveness`; it
halts on the same verdict `ensure_alive` did) → governed timesheet read
→ per-row governed drafts
with `report_spend` + `report_usage` (the 5th draft arrives with the meter
at 96% and is ESCALATED to a human) → `transfer funds` BLOCKED (`D.scope`)
→ an Opus report off the Haiku allow-list FLAGGED (`rogue_model`) → and,
after a real kill, the re-invoked agent halts before any work.

Run it: `bash integration/demo/run_demo.sh` (~30s). A committed real run:
[`docs/capstone-evidence/field-agent-run.log`](capstone-evidence/field-agent-run.log).
The SDK's own mini-demo: `bash packages/field-agent/demo.sh`.

Starting a NEW agent instead? Copy
`packages/field-agent/examples/agent_template.py` and see `examples/`
(one runnable sample per hook, an operator-bootstrap script, a raw-REST
equivalent for non-Python agents, and `run_all.sh` to exercise the lot
against an ephemeral stack).

## 9. Troubleshooting

- **`NoSpendCapError` / 404 on usage** — the governor refuses to meter
  ungoverned spend. `governor set-cap <agent> --from-manifest <manifest>`.
- **401 with `x-field-auth` in the detail** — a secret estate and a client
  without the header. The SDK attaches it automatically; hand-rolled
  `httpx` calls (and the pre-SDK demo agent) do not.
- **Everything is ALLOW that shouldn't be** — the served sentinel defaults
  to `log_only`. Look for `conformance.shadow_block` events in the ledger;
  set `FIELD_SENTINEL_MODE=enforce` where you want real blocks.
- **`AgentKilled` for an agent you never killed** — unknown to the
  registry (fail closed). Register it, or check `agent_id` spelling.
- **`E.spend_cap` ESCALATE on every check** — the manifest declares a
  spend cap but the governor has none configured; set the cap.
