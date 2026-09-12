---
name: field-agent
description: Implement a compliant FIELD-governed agent using the field-agent client SDK (Spin State Labs). Use whenever the user invokes /field-agent, is writing or reviewing code for an agent that must run under FIELD governance, needs the three hooks (governed actions, usage metering, liveness), is doing operator bootstrap (register / cap / policy / mint), integrating a non-Python agent over raw REST, or asks whether an agent is compliant. FIELD is the design-time manifest (the 'field' plugin / /field); field-agent is the build-time code integration. Never claim the SDK governs code that does not call it.
---

# field-agent — implement a compliant FIELD-governed agent

The client SDK is `packages/field-agent` in the field-platform monorepo.
Three hooks, a few lines each: actions checked before they run, LLM usage
metered strictly, liveness polled with a fail-closed halt.

```python
from field_agent import FieldAgent, ActionBlocked, ActionEscalated, AgentKilled

agent = FieldAgent("invoicing-agent", token_id=TOKEN, heartbeat_max_age=30.0)

@agent.governed("draft invoices")            # hook 1: ACTIONS
def draft_invoice(row): ...

agent.checkin()                              # hook 3: LIVENESS (halts if killed; records last_seen)
resp = client.messages.create(...)
agent.report_usage_from(resp, note="INV-001")  # hook 2: USAGE (strict)
```

## Honesty rules (non-negotiable — these define "compliant")

1. **Client, not authority.** The SDK adds ZERO new power; every decision
   is server-side (conformance-sentinel, spend-governor, kill-switch). Its
   only local capability is refusal — raising before ungoverned work runs.
2. **Cooperative perimeter.** An agent that never calls the SDK is NOT
   governed. Never write docs or code comments claiming otherwise. The
   server-side backstop for non-callers: a killed agent's next sentinel
   `/check` is BLOCK; tokens can be revoked; lifecycle-manager finds orphans.
3. **Enforced vs Declared.** Any README you write for a new agent keeps an
   accurate Enforced-vs-Declared table (model:
   `packages/field-agent/README.md`). A governance product that overclaims
   has already failed.
4. **Agents do not self-authorize.** `field_agent.bootstrap` (register/mint)
   is operator-side and deliberately not on the facade. Never import it in
   agent code; the token arrives from outside (arg, env, or a zero-arg
   callable for rotation).
5. **Strict metering stays visible.** `report_usage`/`report_spend` raise on
   failure. Never wrap them in a silent `except: pass` — if fire-and-forget
   is truly wanted, the try/except must be explicit and commented in the
   agent's own code.
6. The product name is the **FIELD platform / Force Field Protocol** —
   never write "Force Field Framework".

## The three hooks + operator flow

Full API knowledge, failure-semantics table, operator bootstrap sequence,
env vars/ports, and troubleshooting: read `integration.md` in this skill
directory. Non-Python agents: read `rest-api.md`. Compliance review rubric:
`checklist.md`.

Quick failure semantics (every compliant agent handles all of these):

| Exception | Meaning | Compliant response |
|---|---|---|
| `ActionBlocked` | BLOCK — or sentinel unreachable (fail-closed) | do not do the action; inspect `.verdict` |
| `ActionEscalated` | ESCALATE — a human has it | skip/queue; never retry-loop to bypass |
| `AgentKilled` | killed / unknown agent | halt now |
| `HeartbeatUnreachable` (⊂ `AgentKilled`) | kill-switch unreachable | halt now — unknown liveness is not liveness |
| `NoSpendCapError` (⊂ `UsageReportError`) | governor has no cap | stop; operator must `governor set-cap` |
| `UsageReportError` | report did not land | spend is unmetered — stop or retry visibly |
| `BootstrapError` | register/mint failed | operator problem, not agent logic |

## Templates (bundled, vendored from the monorepo)

`${CLAUDE_PLUGIN_ROOT}/templates/` — provenance and sync in
`templates/SOURCES.md`:

| File | Use |
|---|---|
| `agent_template.py` | START HERE for a new agent: liveness gate → governed work loop → strict metering, every exception handled honestly |
| `bootstrap_operator.py` | operator setup: manifest → register → cap → policy → mint (prints token id last) |
| `rest_api.sh` | the same three hooks over raw curl — any language |
| `field-manifest-default.yaml` | FIELD manifest template (fill every REPLACE-ME) |
| `example-manifest-invoicing-agent.yaml` | a fully resolved manifest that `field validate` accepts |
| `manifest-schema.json` | the manifest JSON schema (field.spinstatelabs.ca/v1) |

When scaffolding a new agent: copy `agent_template.py`, replace `AGENT_ID`
and the action names, keep the exception structure intact. Actions must
appear in BOTH the token scope and the manifest `delegation.scope`.

## Install (v0.1 reality)

```bash
pip install --no-deps -e packages/field-agent
```

`--no-deps` is mandatory: the `conformance-sentinel` dependency is not on
PyPI (the SDK re-exports its `governed.py` verbatim). v0.1 therefore
requires a field-platform checkout with `field-core` and
`conformance-sentinel` installed editable first. Promoting `governed.py`
into field-core (dropping the service dep) is the recorded v0.2 idea. Do
not present the SDK as pip-installable standalone — that would be an
overclaim.

## Gotchas that bite

- The SERVED sentinel defaults to `FIELD_SENTINEL_MODE=log_only`: everything
  answers ALLOW and the true verdict is shadow-ledgered
  (`conformance.shadow_block`). Demos/tests that want real BLOCKs must
  export `FIELD_SENTINEL_MODE=enforce` before booting the stack.
- `FIELD_SHARED_SECRET` set ⇒ every SDK call carries `x-field-auth`
  automatically (read per request); hand-rolled `httpx`/curl calls must add
  the header themselves (`field_core.authn.auth_headers()`).
- Services are NOT persistent daemons — nothing runs between sessions. Boot
  a stack with `packages/field-agent/demo.sh`, `integration/demo/run_demo.sh`,
  or docker compose before expecting answers.
- Windows cp1252 consoles: keep the template's `sys.stdout.reconfigure`
  UTF-8 preamble.
- Async agents: the SDK is sync `httpx` only in v0.1 — wrap calls in a
  thread.
