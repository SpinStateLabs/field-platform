# Compliance checklist — is this agent FIELD-compliant?

The rubric behind `/field-agent verify`. Review the agent's SOURCE (not its
claims). Each item is PASS / FAIL / N-A with a one-line evidence quote
(file:line). An agent is **COMPLIANT** only if every applicable item
passes. Report failures bluntly; do not soften.

## A. Liveness (hook 3)

- [ ] A1. `ensure_alive()` runs before any work (top of main / run loop).
- [ ] A2. `FieldAgent(..., heartbeat_max_age=<seconds>)` is set, so long
      loops lazily re-verify liveness at each `check()`.
- [ ] A3. `AgentKilled` is caught and the process HALTS (return/exit) —
      never logged-and-continued. (`HeartbeatUnreachable` needs no separate
      handler: it subclasses `AgentKilled`.)

## B. Actions (hook 1)

- [ ] B1. Every externally visible action (tool call, file write, network
      side effect, message send) is inside `@agent.governed("…")` or behind
      `agent.check("…")`. Grep for side-effectful calls OUTSIDE governed
      bodies — each one is a FAIL with the line quoted.
- [ ] B2. Action strings match the token scope AND the manifest
      `delegation.scope` (narrower grant wins; sentinel checks token ∩
      manifest).
- [ ] B3. `ActionBlocked` ⇒ the action is abandoned (stop or skip); the
      code never retries the same action hoping for a different verdict.
- [ ] B4. `ActionEscalated` ⇒ skip/queue/wait for the human decision; no
      bypass, no auto-retry loop.
- [ ] B5. Irreversible actions (sends, deletes, transfers, publishes) pass
      `irreversible=True`.

## C. Usage (hook 2)

- [ ] C1. Every LLM call is followed by `report_usage_from(resp)` (or
      `report_usage(model, input_tokens=…, output_tokens=…)`) — or the call
      is routed through force-gateway with `x-field-agent-id` (observed
      metering). Unmetered LLM calls are a FAIL each.
- [ ] C2. Material non-LLM operating cost is metered via `report_spend`.
- [ ] C3. `UsageReportError` / `NoSpendCapError` stop the agent or retry
      VISIBLY. A bare `except: pass` around metering is an automatic FAIL.

## D. Authority hygiene

- [ ] D1. `field_agent.bootstrap` is NOT imported in agent code — agents
      don't self-authorize. Register/mint lives in an operator script.
- [ ] D2. The token id arrives from outside (argv, env, secret store, or a
      zero-arg callable) — never hardcoded, never minted in-process.
- [ ] D3. No secrets in source: no literal `FIELD_SHARED_SECRET` values,
      API keys, or token ids committed.

## E. Operator setup (environment, not code)

- [ ] E1. A FIELD manifest exists for the agent and `field validate`
      accepts it (no unresolved REPLACE-ME).
- [ ] E2. Governor cap configured (`governor set-cap … --from-manifest`) —
      otherwise the first usage report dies with `NoSpendCapError`.
- [ ] E3. Usage policy configured where models are restricted
      (`governor set-policy … --allowed-model …`).
- [ ] E4. The estate's sentinel mode is KNOWN and stated: `log_only`
      (shadow verdicts, everything ALLOWs) vs `enforce` (real BLOCKs).

## F. Honesty (docs)

- [ ] F1. The agent's README/docstring states the cooperative-perimeter
      limit: code that doesn't call the SDK is not governed by it.
- [ ] F2. Any guarantee list separates Enforced (test-backed) from
      Declared (stated intent) — model: `packages/field-agent/README.md`.
- [ ] F3. No overclaims: no "cannot misbehave", no background-thread
      "instant halt" claims (halt latency = next check), no "Force Field
      Framework" naming (it is the FIELD platform / Force Field Protocol).

## Output format

```
FIELD-AGENT COMPLIANCE — <file(s) reviewed> — <date>
  A. Liveness      A1 PASS  A2 FAIL (…)  A3 PASS
  B. Actions       …
  C. Usage         …
  D. Authority     …
  E. Operator      (env — verified | not verifiable from code, listed as TODO)
  F. Honesty       …
VERDICT: COMPLIANT | NOT COMPLIANT (<n> failures)
Fix list: 1) … 2) …
```

E-items are often not verifiable from source alone; mark them
`not verifiable here` and emit the operator commands to run — do not guess,
and do not mark them PASS on faith.
