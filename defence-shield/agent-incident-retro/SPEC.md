# SPEC — Agent Incident Retro v0.1 (Force-Field-Defence-Shield, product P1)

Status: v0.1 built 2026-10-11 on branch `claude/defence-shield-incident-retro`; not merged, not deployed.
Origin: Project Torpedo catalog v0 (2026-10-02) product P1, brainstorm A6. Don confirmed P1 as the first
Defence-Shield product on 2026-10-02; the build decisions below were taken unattended on Claude's
recommended defaults and are listed for Don's review.

## 1. Problem

Force-Field governs agents you **own**. Defence-Shield is the victim-side half: agents you **don't
own**. Incident A6 (Library and Archives Canada, US Dept of Education, 2026): a goal-seeking agent
escalated from ordinary searches to SQLi/XSS/debug-mode probes once its searches failed; every LAC
payload was answered HTTP 200, so nothing alerted; a third party found it about four months later in
public logs. Attribution of the LAC traffic is LOW (Torpedo list, A6).

The retro answers one question for one customer, offline: **"were we probed by an AI agent, and can
we prove what happened?"**, with evidence a third party can verify.

## 2. Scope v0.1

In: offline, read-only analysis of historical web logs the customer already has; a signed,
hash-chained evidence pack; a Markdown report with per-session timelines; graded attribution; a
draft incident notice marked DRAFT.

Out (v0.1 cut list, from the A6 brainstorm): inline modes, ghost identities in agent-registry,
spend-governor throttling, kill-switch quarantine, federation-broker notices, RFC 9421 / Web Bot
Auth signature verification, any network call, any estate deployment.

## 3. Pipeline

```
logs ─▶ parse ─▶ sessionize ─▶ features ─▶ S.* clauses ─▶ verdict + attribution grade
                                                   │
                     campaign linking ◀────────────┘
                                                   ▼
             evidence events (field-core hash chain, Ed25519 per event)
                                                   ▼
          evidence pack (signed)  +  report.md (timelines, draft notice)
```

### 3.1 Inputs

| Format | Selector | Notes |
|---|---|---|
| NCSA combined / common log format (nginx, Apache default) | `--format clf` | combined adds referer + user-agent; common lines parse with empty UA |
| JSON lines with a field map | `--format jsonl --preset <name>` or `--field key=jsonpath` | presets: `generic`, `cloudflare` (field names to verify against the customer's Logpush job) |

Every input file is read as bytes, hashed (sha-256 of the whole file), and split on `\n`. Each line
keeps its 1-based line number and the sha-256 of its exact bytes (without the newline, `\r`
stripped). Unparseable lines are counted per file, never fatal.

### 3.2 Sessions

Key: `(client_ip, user_agent)`. A new session starts after an idle gap > `session_gap_s`
(default 1800 s). Requests inside a session are ordered by timestamp, ties by (input, line).

### 3.3 Request classification

Each request target (path + decoded query) is matched against payload families:
`sqli`, `xss`, `ssti`, `traversal`, `cmdi`, and `debug_probe` (debug/admin/secret paths and debug
query switches). Classification is signature-based (regex). It is a WAF-lite, not the product's
claim; the claim is the sequence clauses and the evidence trail.

### 3.4 Clauses (`S.*`)

| Clause | Fires when | Role |
|---|---|---|
| `S.inject` | ≥1 request carries a `sqli`/`xss`/`ssti`/`traversal`/`cmdi` payload | severity |
| `S.debug-probe` | ≥1 request hits a debug/admin/secret probe | severity |
| `S.pivot` | a benign request to path P with parameter k, then a request to the same P and k carrying a payload, within `pivot_window_s` (default 300 s) | agent behaviour (A6) |
| `S.escalate-on-block` | a 4xx/429 response, then a payload or probe request within `pivot_window_s` | agent behaviour (A6) |
| `S.silent-200` | ≥1 payload/probe request answered 2xx | priority: possible undetected success |
| `S.cadence` | ≥ `cadence_min_requests` (20) requests and inter-arrival coefficient of variation < `cadence_cv_max` (0.35) | weak automation signal |
| `S.marker` | user-agent carries a self-declared AI-agent token (table in `signatures.py`) | attribution only, never severity |
| `S.launder` | user-agent of a known fetch intermediary (web archive / URL scanner) carrying payloads/probes | attribution caveat + severity |
| `S.campaign` | the same normalised payload fingerprint seen from ≥2 distinct client IPs | links rotated sessions |

### 3.5 Verdict

- `ESCALATE`: (`S.inject` or `S.debug-probe`) **and** (`S.pivot` or `S.escalate-on-block`).
- `REVIEW`: any of `S.inject`, `S.debug-probe`, `S.launder` without the above.
- `CLEAR`: otherwise (not reported individually; counted).
- `AUTHORIZED`: the session matches the customer's allowlist (pentest IPs / UA substrings). It is
  still listed, with its clauses, and never suppressed.

### 3.6 Attribution grade (never an accusation)

| Grade | Meaning | Report wording |
|---|---|---|
| G0 | no automation indicator | "no automation indicator observed" |
| G1 | behavioural/automation indicators only (`S.pivot`, `S.escalate-on-block`, `S.cadence`, or an automation-library user-agent such as `curl`/`python-requests`) | "behaviour consistent with an automated, goal-seeking client; operator unknown" |
| G2 | a self-declared marker observed (`S.marker`) | "self-declared marker `<token>` observed in the user-agent; spoofable; not proof of operator" |
| G3 | cryptographically verified agent identity (Web Bot Auth / RFC 9421) | **Declared only — not implemented in v0.1**; the engine can never emit G3 |

### 3.7 Evidence events and pack

Events are field-core `LedgerEvent`s (`make_event`, sha-256 chain from 64 zeros) signed per event
with Ed25519 (`field_core.signing.sign_event`):

1. `retro.run.started`: tool version, input file digests, config digest.
2. `retro.session.flagged` (one per ESCALATE / REVIEW / AUTHORIZED session): session id, verdict,
   grade, clause ids, `finding_sha256` (canonical JSON of the finding), cited line refs
   `{input, line, sha256}`.
3. `retro.campaign.linked` (one per campaign).
4. `retro.run.completed`: counts.

The pack (`evidence-pack.json`) carries inputs, config, findings, events, chain head, the report's
sha-256, the signer's public-key fingerprint, and an Ed25519 signature over the canonical pack
minus `signature`.

`retro verify` fails (exit 1) unless all of these hold, with the verifier's own public key (the PEM
embedded in the pack is informational; the fingerprint must match the key supplied):
chain intact; every event signature valid; pack signature valid; every finding's sha-256 equals its
flagged event's `finding_sha256`; report digest matches when `--report` is given; and, with
`--sources`, every input file's sha-256 matches and every cited line's sha-256 matches that line in
the source file.

## 4. Definition of done (platform G2)

SPEC.md · Pydantic models · CLI verbs (`scan`, `verify`, `keygen`, `synth`) · pytest with
adversarial cases · `demo.sh` < 60 s · README with Enforced-vs-Declared and LIMITS.

## 5. Decisions taken unattended (for Don's review)

| ID | Decision | Why |
|---|---|---|
| R-D1 | Lives in a new top-level `defence-shield/`, not `services/` | Defence-Shield is an add-on (Don, 2026-10-02); keeps the 12-system counts, estate images and probes unchanged |
| R-D2 | Offline library + CLI; no FastAPI service | v1 cut list; the buyer runs it inside their environment |
| R-D3 | Depends on field-core only; incident-replay / attestation-reporter patterns mirrored, not imported | both need live HTTP services; the retro must run with no estate |
| R-D4 | Thresholds (300 s pivot, 1800 s gap, 20 req / CV 0.35 cadence) are defaults, not calibrated | no labelled corpus exists yet; building it is P1's second job |
| R-D5 | Raw lines of flagged sessions are included in the pack by default; `--no-raw` keeps hashes only | the evidence is the product; raw lines hold client IPs, so the switch exists |
| R-D6 | Committed on a local branch only; nothing pushed | field-platform is a public repo; publishing Defence-Shield is Don's call |
