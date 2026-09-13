# FIELD Platform — Architecture

Reference implementation of the **Force Field Protocol**: FORCE (runtime
prompt protocol) + FIELD (design-time governance — Federation · Identity ·
Enforcement · Ledger · Delegation). Thirteen packages: `field-core` (the
schema source of truth) and twelve services, each owned by a named
executive function.

## 1. System architecture (layers, ports, dependencies)

```mermaid
flowchart TB
    subgraph AGENTS["Governed agents"]
        AGENT["invoicing-agent (demo)<br/>field-agent SDK (@governed · usage · heartbeat)"]
    end

    subgraph EDGE["Phase 4 — Edge & Executive"]
        FED["federation-broker :8010<br/>F · CIO/GC"]
        LIFE["lifecycle-manager :8012<br/>I+D · CIO/CHRO"]
        ATT["attestation-reporter :8013<br/>all · CEO/board"]
    end

    subgraph INTEL["Phase 3 — Intelligence"]
        REPLAY["incident-replay :8007<br/>L · CISO"]
        XWALK["compliance-crosswalk :8008<br/>law · CCO/GC"]
        GW["force-gateway :8009<br/>FORCE · CTO/CDO"]
    end

    subgraph ENFORCE["Phase 2 — Enforcement"]
        SENT["conformance-sentinel :8004<br/>E · CISO"]
        KILL["kill-switch :8005<br/>E · CEO/CISO"]
        GOV["spend-governor :8006<br/>E · CFO/CTO"]
    end

    subgraph SPINE["Phase 1 — Spine"]
        REG["agent-registry :8001<br/>I · CIO"]
        LED["sealed-ledger :8002<br/>L · CFO/audit"]
        DEL["delegation-authority :8003<br/>D · GC"]
    end

    CORE["packages/field-core<br/>manifest models · validate · hash-chain ·<br/>tokens · verdicts · clients · authn · signing"]

    AGENT -->|"/check before every tool call"| SENT
    AGENT -->|"/heartbeat poll"| KILL
    AGENT -->|"/spend self-report"| GOV
    AGENT -.->|"LLM calls via proxy"| GW

    SENT --> REG
    SENT --> DEL
    SENT --> GOV
    SENT --> LED
    KILL --> REG
    KILL --> LED
    GOV --> LED
    DEL --> REG
    DEL --> LED
    FED --> LED
    LIFE --> REG
    LIFE --> DEL
    LIFE --> LED
    LIFE -.->|"--auto-kill-orphans only"| KILL
    REPLAY --> LED
    REPLAY --> REG
    REPLAY --> DEL
    ATT --> REG
    ATT --> LED
    ATT --> DEL
    ATT --> GOV
    GW -.->|"token spend"| GOV
    GW -->|"injected FORCE block"| UPSTREAM["Anthropic Messages API<br/>(or deterministic mock)"]
    XWALK -.->|"evidence collection"| REG
    XWALK -.-> LED

    SPINE --- CORE
```

Solid arrows = required runtime dependency. Dotted = optional/best-effort.
Every service imports `field-core`; no service redefines schema. Agents
integrate through `packages/field-agent` (the client SDK: sentinel-checked
actions, strict usage metering, fail-closed heartbeat — a client, not an
authority; see `docs/INTEGRATION.md`).

## 2. Logical diagram — the Force Field Protocol mapped to systems

```mermaid
flowchart LR
    subgraph PROTOCOL["Force Field Protocol"]
        subgraph FIELDL["FIELD — design-time governance"]
            F["F · Federation"]
            I["I · Identity"]
            E["E · Enforcement"]
            L["L · Ledger"]
            D["D · Delegation"]
        end
        subgraph FORCEL["FORCE — runtime prompt protocol"]
            FO["Forbid flattery · Oppose premise ·<br/>Reference sources · Chain-of-thought ·<br/>Express uncertainty"]
        end
    end

    F --> FEDS["federation-broker<br/>contracts + Ed25519-signed manifests"]
    I --> REGS["agent-registry<br/>+ shadow-agent discovery"]
    I --> LIFES["lifecycle-manager<br/>orphans + re-attestation"]
    E --> SENTS["conformance-sentinel<br/>ALLOW / BLOCK / ESCALATE + clause id"]
    E --> KILLS["kill-switch<br/>halt + heartbeat + timed drills"]
    E --> GOVS["spend-governor<br/>escalate-before-cap, integer cents"]
    L --> LEDS["sealed-ledger<br/>sha-256 hash chain, first-break detection"]
    L --> REPS["incident-replay<br/>RACI post-mortems"]
    D --> DELS["delegation-authority<br/>scoped expiring revocable tokens"]
    FO --> GWS["force-gateway<br/>verbatim preset injection + telemetry"]
    FIELDL --> XW["compliance-crosswalk<br/>declared vs evidenced, grounded citations"]
    PROTOCOL --> ATTS["attestation-reporter<br/>board pack — no number without a source"]
```

**The honesty line, structurally:** a manifest *declares* governance
(field-core validates it); the spine *records* it; the enforcement layer
*makes it real*; the intelligence layer *proves it after the fact*; the
executive layer *reports it with sources*.

## 3. The enforcement decision (sentinel `/check`, first failing clause wins)

```mermaid
flowchart TD
    START(["/check agent_id + action + token"]) --> C1{"1 · sealed-ledger<br/>reachable?"}
    C1 -- no --> B1["BLOCK L.unreachable<br/>(unloggable action may not run)"]
    C1 -- yes --> C2{"2 · registered<br/>and active?"}
    C2 -- "unregistered" --> B2["BLOCK R.unregistered"]
    C2 -- killed --> B3["BLOCK E.kill_switch"]
    C2 -- yes --> C3{"3 · manifest resolves<br/>+ field validate OK?"}
    C3 -- no --> B4["BLOCK I.manifest"]
    C3 -- yes --> C4{"4 · token presented,<br/>active, bound to agent?"}
    C4 -- missing --> B5["BLOCK D.token"]
    C4 -- expired --> B6["BLOCK D.expired"]
    C4 -- revoked --> B7["BLOCK D.revoked"]
    C4 -- yes --> C5{"5 · action in token scope<br/>∩ manifest scope?"}
    C5 -- no --> B8["BLOCK D.scope<br/>(narrower grant wins)"]
    C5 -- yes --> C6{"6 · irreversible?"}
    C6 -- "policy: forbid" --> B9["BLOCK E.irreversible"]
    C6 -- "policy: human approval" --> E1["ESCALATE E.irreversible"]
    C6 -- "no / allow_with_ledger" --> C7{"7 · escalation<br/>trigger match?"}
    C7 -- yes --> E2["ESCALATE E.escalation_trigger"]
    C7 -- no --> C8{"8 · spend state<br/>from governor?"}
    C8 -- "cap reached" --> B10["BLOCK E.spend_cap"]
    C8 -- "threshold crossed" --> E3["ESCALATE E.spend_threshold"]
    C8 -- OK --> ALLOW(["ALLOW — verdict logged to ledger,<br/>like every other outcome"])
```

## 4. Capstone scenario (sequence)

```mermaid
sequenceDiagram
    autonumber
    actor Human as Controller (human)
    participant A as invoicing-agent
    participant S as sentinel :8004
    participant R as registry :8001
    participant De as delegation :8003
    participant G as governor :8006
    participant K as kill-switch :8005
    participant Le as ledger :8002

    Human->>R: register agent + manifest_ref
    Human->>G: set-cap from manifest ($500/day, escalate 80%)
    Human->>De: mint token (scope, 1h TTL)
    De->>Le: delegation.mint (ledger-first, fail-closed)
    loop each invoice
        A->>S: /check "draft invoices"
        S->>Le: conformance.allow
        A->>G: /spend $120
    end
    A->>S: /check draft #5 (meter at 96%)
    S-->>A: ESCALATE E.spend_threshold → human queue
    A->>S: /check "transfer funds" (rogue)
    S-->>A: BLOCK D.scope — function body never runs
    Human->>K: drill
    K->>R: status=killed → verify → restore (~53 ms)
    Human->>Le: incident-replay → RACI post-mortem
    Human->>Le: attest render → board pack (every number sourced)
```

## 5. Trust model & deliberate asymmetries

| Property | Posture |
|---|---|
| Authority **creation** (mint) | Ledger-first, **fail-closed** — unauditable authority must not exist |
| Authority **destruction** (kill) | **Act-first**, best-effort logging — a halt never waits on the audit trail |
| Dependency outages at the sentinel | Every one maps to a BLOCK clause (fail-closed) |
| Inter-service authn | `FIELD_SHARED_SECRET` → `x-field-auth` middleware on all APIs when set; `/health` open; TLS = fronting proxy |
| Federation authenticity | Ed25519 manifest signatures, required when the contract holds the counterparty key; keyless contracts = consistency-only (stated) |
| Perimeter | Cooperative in v0.1: `@governed` + gateway route through checks; a process that never asks is contained by revocation + kill + discovery, not interception |

## 6. Storage & event taxonomy

| Service | Store | Key ledger events |
|---|---|---|
| sealed-ledger | hash-chained JSONL segments: `ledger/events.jsonl` (open) + `events-<n>.jsonl` (closed) + `events.segments.journal`, `legal_hold.json`; archived segments with `<file>.segment.json` sidecars under `ledger-archive/` (C2) | it *is* the ledger; its own records are `ledger.segment.rotated`, `ledger.retention.applied`, `ledger.legal_hold.placed\|released` |
| agent-registry | SQLite `agents.sqlite3` | `registry.registered`, `registry.status_changed`, `registry.updated`, `registry.attested` — emitted when a ledger is wired (injected, or `FIELD_LEDGER_URL` set); silent otherwise, and the gap is then visible as missing `registry.*` events |
| delegation-authority | SQLite `tokens.sqlite3` | `delegation.mint`, `delegation.revoke` |
| conformance-sentinel | stateless (mtime manifest cache) | `conformance.allow\|block\|escalate` |
| kill-switch | SQLite `killswitch/heartbeats.sqlite3` (check-ins only — the registry is still the authority on status) | `kill.agent`, `kill.domain`, `kill.revive`, `kill.drill.start|complete|restore_failed`, `kill.endpoint_called|failed|skipped` |
| spend-governor | SQLite `spend.sqlite3` | `spend.recorded`, `spend.escalate`, `spend.cap_reached`, `spend.escalation_resolved` |
| federation-broker | SQLite `contracts.sqlite3` | `federation.allow\|block` |
| lifecycle-manager | last sweep + last tick under `lifecycle/` (the served API; the CLI job itself is stateless) | `lifecycle.expiring_authority`, `lifecycle.reattestation_due`, `lifecycle.orphan`, `lifecycle.decommissioned`, `lifecycle.tick_skipped` |
| incident-replay / crosswalk / attestation | stateless query engines | (readers, not writers) |
| force-gateway | in-memory telemetry | (spend forwarded to governor) |

All service data lives under `FIELD_DATA_DIR` (default `./var`, one shared
volume in compose).
