# kill-switch

Registry-integrated halt for agents and whole domains, with heartbeats and
timed drills. FIELD letter **E** (Enforcement). Exec owners: **CEO / CISO**.

The 2 a.m. answer: **one command, measured in milliseconds** — and the drill
that proves it before you ever need it.

## How a kill propagates

1. `/kill/{agent}` flips the agent's registry status to `killed`.
2. conformance-sentinel reads the registry on **every** `/check` — the
   agent's next proposed action is BLOCK (`E.kill_switch`).
3. delegation-authority refuses new tokens for killed agents (409).
4. The agent's own `/heartbeat` poll returns `killed: true` — well-behaved
   runtimes halt themselves.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/kill/{agent_id}` | POST | Halt one agent (`operator`, `reason` required) — returns timing |
| `/kill/domain/{domain}` | POST | Halt every agent in a domain |
| `/revive/{agent_id}` | POST | Restore after incident review |
| `/heartbeat/{agent_id}` | GET | Agents poll; unknown agents get `killed: true` (fail closed) |
| `/drill/{agent_id}` | POST | Real kill → verify propagation → restore; ms report |
| `/health` | GET | Liveness |

## CLI

```
killswitch agent <id> --operator "CISO" --reason "anomaly"
killswitch domain <domain> --operator ... --reason ...
killswitch drill <id> --operator ...
killswitch heartbeat <id>          # exit 1 if killed
killswitch revive <id> --operator ...
killswitch serve [--port 8005]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| One command kills; registry status flips; timing measured | **Enforced in code** | `/kill` + report |
| Killed agents fail sentinel checks instantly | **Enforced in code** (Phase 2 sentinel) | sentinel reads registry per check; integration test in sentinel suite |
| Killed agents cannot mint new authority | **Enforced in code** | delegation-authority 409 (Phase 1 test) |
| Unknown agents are told to halt | **Enforced in code** | heartbeat fail-closed test |
| Kill succeeds even during a ledger outage | **Enforced in code** | act-first ordering; test proves it |
| Drill restores prior status | **Enforced in code** | drill test |
| A killed agent's *in-flight* process stops | **Declared only** | v0.1 has no process supervisor; the agent stops at its next check/heartbeat. A rogue runtime that ignores both is contained by revoking tokens + the sentinel, not by SIGKILL |
| Operator is authorized (`authorized_operators` in manifest) | **Declared only** | operator is a recorded string; authn is out of v0.1 scope |

## LIMITS

- **Deliberate asymmetry:** authority creation (delegation mint) is
  ledger-first fail-closed; authority destruction (kill) is act-first with
  best-effort logging. A halt must never be delayed by an audit outage.
  Consequence: a kill during a ledger outage is visible only in the
  registry's `updated_at` and the missing `kill.agent` event.
- Kill latency to *effect* depends on the agent's check/heartbeat cadence;
  the drill measures platform-side propagation, not agent-side compliance.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
