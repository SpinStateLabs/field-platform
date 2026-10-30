# FIELD Platform — Architecture

Reference implementation of the **Force Field Protocol**: FORCE (runtime
prompt protocol) + FIELD (design-time governance — Federation · Identity ·
Enforcement · Ledger · Delegation). The code is `field-core` (the
schema source of truth), the `field-agent` client SDK (`packages/`), and
fourteen services (`services/`), each owned by a named executive function. Two of the fourteen
are clients of the others rather than a layer of their own: `ops-console` and
`claude-approver` (below the diagram).

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

    subgraph CLIENTS["Clients of the layers (not a FIELD letter)"]
        OPSC["ops-console :8011<br/>UI · reads twelve services"]
        APPR["claude-approver :8014<br/>pilot client"]
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
    XWALK -.->|"evidence reads"| DEL
    XWALK -.->|"evidence reads"| GOV
    REG -.->|"only if FIELD_LEDGER_URL is set"| LED
    GW -.->|"enforce mode only: 503 without it"| SENT
    GW -.->|"events, best-effort"| LED
    LIFE -.->|"CLI client only"| GOV
    APPR -.-> SENT
    APPR -.-> KILL
    APPR -.-> GOV

    SPINE --- CORE
```

Solid arrows = required runtime dependency. Dotted = optional/best-effort.
The dotted arrows added for the services that were missing from this diagram
are each marked from the code: registry to ledger exists only when
`FIELD_LEDGER_URL` is set (`services/agent-registry/src/agent_registry/api.py:187`);
gateway to sentinel is used only under `FORCE_GATEWAY_ENFORCE`, where an
unreachable or non-200 sentinel answers 503 and makes no upstream call
(`services/force-gateway/src/force_gateway/api.py:36-37`), and gateway events
are best-effort (`api.py:38-39`); lifecycle-manager to governor is the CLI's
estate client (`services/lifecycle-manager/src/lifecycle_manager/cli.py:187`,
`:211`), not the served API; crosswalk to delegation and governor are the
evidence reads (`services/compliance-crosswalk/src/compliance_crosswalk/api.py:224-232`,
a failed read yields none); claude-approver calls governor, kill-switch and
sentinel (`FIELD_GOVERNOR_URL`, `FIELD_KILLSWITCH_URL`, `FIELD_SENTINEL_URL` in
`services/claude-approver/src/claude_approver/`). I did not judge whether the
claude-approver arrows are required. `ops-console` is a UI: it reads
attestation, crosswalk, delegation, federation, gateway, governor, kill-switch,
ledger, lifecycle, registry, replay and sentinel by their `FIELD_*_URL`
variables (twelve of the other thirteen) and forwards a human's operator
credentials only on guarded writes; it keeps no store of its own, and the only
ledger records it writes are `operator.refused` for a refused human action
(`services/ops-console/src/ops_console/api.py:377-398`).
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
    Note over Human,Le: demo figures, see the note under this diagram
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

The amounts and timings in this sequence are demo figures, not measurements of
an estate. The $500/day cap, the $120 spend and the 96% meter appear in
`docs/capstone-evidence/field-agent.md:14-18`; the 1 h token lifetime I did not
find in an artifact; the drill figure here (~53 ms) differs from the one run
recorded in `docs/capstone-evidence/field-agent-run.log:33` (kill confirmed
43.6 ms, total 56.3 ms), and I do not know where ~53 ms comes from.

## 5. Trust model & deliberate asymmetries

| Property | Posture |
|---|---|
| Authority **creation** (mint) | Ledger-first, **fail-closed** — unauditable authority must not exist |
| Authority **destruction** (kill) | **Act-first**, best-effort logging — a halt never waits on the audit trail |
| Dependency outages at the sentinel | Every one maps to a BLOCK clause (fail-closed) |
| Inter-service authn | `FIELD_SHARED_SECRET` → `x-field-auth` middleware on all APIs when set; `/health` open; TLS = fronting proxy |
| Federation authenticity | Ed25519 manifest signatures: an inbound crossing needs a contract key and a valid signature (Don D-19, C-175); a keyless contract is valid outbound only |
| Perimeter | Cooperative in the default posture: `@governed` + gateway route through checks; a process that never asks is contained by revocation + kill + discovery, not interception. With `FORCE_GATEWAY_ENFORCE` on, the gateway is also an enforcement point at the LLM egress: it refuses with 401, 403 or 503 and makes no upstream call when identity, authority or the sentinel is missing (`services/force-gateway/src/force_gateway/api.py:25-37`) |

## 6. Storage & event taxonomy

| Service | Store | Key ledger events |
|---|---|---|
| sealed-ledger | hash-chained JSONL segments: `ledger/events.jsonl` (open) + `events-<n>.jsonl` (closed) + `events.segments.journal`, `legal_hold.json`; archived segments with `<file>.segment.json` sidecars under `ledger-archive/` (C2) | it *is* the ledger; its own records are `ledger.segment.rotated`, `ledger.retention.applied`, `ledger.legal_hold.placed\|released` |
| agent-registry | SQLite `agents.sqlite3` | `registry.registered`, `registry.status_changed`, `registry.updated`, `registry.attested` — emitted when a ledger is wired (injected, or `FIELD_LEDGER_URL` set); silent otherwise, and the gap is then visible as missing `registry.*` events |
| delegation-authority | SQLite `tokens.sqlite3` (`tokens`, plus the v1.2 D1e side table `token_spend_ceilings`: a roster row's `max_spend_usd` stamped at mint) | `delegation.mint`, `delegation.revoke` |
| conformance-sentinel | stateless (mtime manifest cache) | `conformance.allow\|block\|escalate`, `conformance.shadow_*` (log-only), `sentinel.metering_gap` (a metering post on an ALLOW got no 201; D1), `sentinel.judge` |
| kill-switch | SQLite `killswitch/heartbeats.sqlite3` (check-ins only — the registry is still the authority on status) | `kill.agent`, `kill.domain`, `kill.revive`, `kill.drill.start|complete|restore_failed`, `kill.endpoint_called|failed|skipped` |
| spend-governor | SQLite `spend.sqlite3` (`spend` gains `action`/`source` at open in D1; `rate_limits` table) | `spend.recorded`, `spend.escalate`, `spend.cap_reached`, `spend.escalation_resolved`, `usage.recorded`, `spend.rate_limit_declared_unenforced` |
| federation-broker | SQLite `contracts.sqlite3` | `federation.allow\|block` |
| lifecycle-manager | last sweep + last tick under `lifecycle/` (the served API; the CLI job itself is stateless) | `lifecycle.expiring_authority`, `lifecycle.reattestation_due`, `lifecycle.orphan`, `lifecycle.decommissioned`, `lifecycle.tick_skipped` |
| incident-replay / attestation | stateless query engines | (readers, not writers) |
| ops-console | none (a UI; no SQLite in its source) | `operator.refused` (`services/ops-console/src/ops_console/api.py:377-398`); the writes it forwards are ledgered by the services that receive them |
| claude-approver | `$FIELD_DATA_DIR/claude-approver/usage-cursor.json` (`services/claude-approver/src/claude_approver/core.py:20-22`) | (none of its own: it calls governor, kill-switch and sentinel) |
| compliance-crosswalk | `crosswalk_stale_flags.json` (flags, history, regwatch `sources`, `last_check`) + its zero-byte `.lock` sidecar (D4) | (none: flags are set by regwatch or `set-stale`, cleared by name on the CLI) |
| force-gateway | SQLite `gateway/telemetry.sqlite3` (D2) | `gateway.bypass` (`api.py:651`), `gateway.drift_alert` (`api.py:711`), `gateway.refused` (`api.py:545`), `gateway.shadowed` (`api.py:572`), `gateway.tool_refused` (`api.py:633`), `gateway.passthrough` `{client_host, agent_id}` (secretless estates only; `agent_id` is the caller's `x-field-agent-id`, null for the platform judges); token spend forwarded to the governor, a passthrough naming an agent included |

All service data lives under `FIELD_DATA_DIR` (default `./var`, one shared
volume in compose).
