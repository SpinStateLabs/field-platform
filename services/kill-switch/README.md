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
5. **Best-effort agent-side signal (v1.2).** After the flip, the service
   resolves the registry record's `manifest_ref` and calls that manifest's
   `enforcement.kill_switch.endpoint`, 2 s timeout. It is a *signal*, not a
   process stop, and it is **off unless `FIELD_KILL_ENDPOINT_ALLOWLIST`
   names the endpoint's host** — see the two guards below.

### The two guards on the outbound signal

**SSRF allowlist (mandatory).** `FIELD_KILL_ENDPOINT_ALLOWLIST` is a
comma-separated host list read *per call*. Unset or blank means the call is
skipped (`allowlist_unset`) and nothing is sent. The compared value is
`urlsplit(endpoint).hostname` by **exact string match**, never a substring or
suffix test: `http://halt.allowed.host@169.254.169.254/latest/meta-data`
(the allowlisted name is only userinfo) and `halt.allowed.host.evil.com`
(suffix) both contain an allowlisted name and are both refused — there is a
test for each. Non-`http(s)` schemes are skipped (`non_http_endpoint`), which
is what a FIELD 1.1.0 `method: file` kill switch becomes. Unparseable methods
are skipped (`unsupported_method`). The endpoint URL is **never** echoed into
the report or the ledger — host only, because a manifest URL can carry
credentials.

**Self-call guard (mandatory, two mechanisms).** Every manifest this service
can resolve today points back at its own `/kill/{agent}`, so without a guard a
kill recurses. Both are implemented: the outbound call carries
`x-field-kill-origin: kill-switch` and an incoming request carrying that
header never signals onward; independently, an endpoint whose path ends in
`/kill/{agent_id}` or contains `/kill/domain/` is skipped (`self_endpoint`).
The path heuristic alone would false-skip a legitimate third-party hook that
happens to use that path shape, which is why the header exists too.

An idempotent re-kill still sends the signal: the registry flip is what is
idempotent; repeating the signal is the point of repeating the command.

The signal carries the kill's reason in `x-field-kill-reason`,
percent-encoded and capped at 512 characters (v1.2 X3), so the agent can tell
which kill halted it. The GB10 `canary-agent` (`packages/field-agent`,
`python -m field_agent.canary serve`) echoes the nonce it parses from a
reason `x3-<nonce>` and reports it on `GET /status`.

Every outcome is ledgered as `kill.endpoint_called` / `kill.endpoint_failed` /
`kill.endpoint_skipped` and returned on `KillReport.endpoint_result`.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/kill/{agent_id}` | POST | Halt one agent (`operator`, `reason` required) — returns timing; **409 for a `retired` agent** |
| `/kill/domain/{domain}` | POST | Halt every agent in a domain; retired agents are skipped and listed in `skipped_retired` |
| `/revive/{agent_id}` | POST | Restore after incident review; **409 for a `retired` agent** |
| `/heartbeat/{agent_id}` | GET | Agents poll; unknown agents get `killed: true` (fail closed). **Never writes** |
| `/heartbeat/{agent_id}` | POST | Check-in: records `last_seen`, then answers with the SAME semantics as the GET |
| `/liveness?stale_after=SECONDS` | GET | Registry-active agents with no check-in inside the window, plus the live ones |
| `/drill/{agent_id}` | POST | Real kill → verify propagation → restore; ms report; **409 for a `retired` agent** |
| `/health` | GET | Liveness probe (the only open path) |

Check-ins live in SQLite at `$FIELD_DATA_DIR/killswitch/heartbeats.sqlite3`
— this service is no longer stateless. An unregistered check-in is recorded
with status `unregistered`, so a shadow agent nobody registered surfaces on
`GET /liveness` instead of staying invisible, and is still told to halt.

## CLI

```
killswitch agent <id> --operator "CISO" --reason "anomaly"
killswitch domain <domain> --operator ... --reason ...
killswitch drill <id> --operator ...
killswitch heartbeat <id>          # read-only poll; exit 1 if killed
killswitch checkin <id>            # POST a check-in; exit 1 if killed
killswitch liveness --stale-after 300
killswitch revive <id> --operator ...
killswitch serve [--port 8005]
```

Agents check in through the SDK (`FieldAgent.checkin()`, `fieldagent checkin
<id>`) or, for non-Python skills, `Send-FieldCheckin` in
`tools/field-rest.ps1`. `killswitch checkin` is an operator/debug verb.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| One command kills; registry status flips; timing measured | **Enforced in code** | `/kill` + report |
| Killed agents fail sentinel checks instantly | **Enforced in code** (Phase 2 sentinel) | sentinel reads registry per check; integration test in sentinel suite |
| Killed agents cannot mint new authority | **Enforced in code** | delegation-authority 409 (Phase 1 test) |
| Unknown agents are told to halt | **Enforced in code** | heartbeat fail-closed test |
| Kill succeeds even during a ledger outage | **Enforced in code** | act-first ordering; test proves it |
| Drill restores prior status | **Enforced in code** | `try/finally` around the whole drill; a test raises between the flip and the restore and asserts the agent is `active` again. A failing restore reports `restored: false` and ledgers `kill.drill.restore_failed` rather than masking the original error |
| Resolvable kill endpoints — the agent's own halt endpoint is actually called | **Enforced in code when `FIELD_KILL_ENDPOINT_ALLOWLIST` names the host** | one shipped manifest declares an agent-side endpoint: `canary-gb10` → `http://canary-agent:8090/halt`, the GB10 `canary-agent` compose service (profile `x3`, v1.2 X3); every other manifest points at this service and is skipped as `self_endpoint`. Both estates run with the allowlist unset until arming step A6 sets `canary-agent` on the GB10 only, so until then every kill ledgers `endpoint_skipped`; Fly has no agent-side endpoint until D7. The real app calling the real canary endpoint over a socket with the real manifest (kill ⇒ `called` and the canary's `/status` halted with the same nonce; drill ⇒ `endpoint_confirmed_ms`) is `packages/field-agent/tests/test_canary_agent.py`; not yet run on the estate. Adversarial tests: metadata-IP endpoint with the allowlist unset AND set, userinfo and suffix host tricks, header-marked self call, allowlisted host raising (kill still 200, `failed`), allowlisted 200 (`called`) |
| The endpoint call cannot be steered off the allowlist (no SSRF) | **Enforced in code** | exact `urlsplit(...).hostname` match; scheme restricted to http/https. Every weakening of the comparison has its own payload: **substring** (`http://allowed.host@169.254.169.254/`), **prefix** (`allowed.host.evil.com`) and **suffix** (`notallowed.host`, a separate registrable domain that `.endswith("allowed.host")` accepts). A bare entry does not admit its subdomains either — the allowlist is a set of hosts, not of zones |
| A redirect cannot walk the halt signal off the allowlist | **Enforced in code** | the outbound client is built by `new_endpoint_client()` with `follow_redirects=False`; the test drives real httpx redirect machinery over a mock transport with the flag read off that client, so an allowlisted host answering `302 Location: http://169.254.169.254/` is returned as a 302 and the metadata IP is never reached |
| The heartbeat database lands under `$FIELD_DATA_DIR` | **Enforced in code** | `_default_store_path()` → `$FIELD_DATA_DIR/killswitch/heartbeats.sqlite3` (`./var` unset); tests pin the path, pin that the app's lazily built store is the one at that path, and pin that a kill-switch nobody checks in to creates no file at all |
| A halt signal never recurses into this service | **Enforced in code** | `x-field-kill-origin` header short-circuit **and** a path-SHAPE skip covering every route this service serves — `/kill/`, `/kill/domain/`, `/revive/`, `/drill/`, `/heartbeat/`, `/liveness`, `/health` — whichever agent the path names. Parametrized test per route, plus a test that a genuinely foreign path is still called so the guard cannot be satisfied by refusing everything. The shape guard replaced an id-matching one that recognised only `/kill/{the-agent-being-killed}`: a manifest pointing at `/heartbeat/{another-agent}` slipped through, and the outbound signal forged a check-in that `GET /liveness` then reported as live |
| The halt signal carries the kill's reason and cannot inject a header with it | **Enforced in code** | `x-field-kill-reason` = `quote(reason[:512], safe="")`; tests: the decoded header equals the reason on kill, re-kill and drill, and a reason with CR/LF, a forged header line and non-ASCII goes through a real httpx client as one ASCII header whose decoding is the first 512 characters |
| Endpoint credentials never reach the report or the ledger | **Enforced in code** | host-only `EndpointResult`; URL-scrubbing test with a password and a query secret in the manifest endpoint |
| A domain kill survives one broken agent | **Enforced in code** | per-agent outcomes in `results[]`; a registry fault on one agent is recorded, not raised mid-loop; route stays 200; tests for a failing endpoint and for a per-agent registry fault |
| Heartbeats: server-side liveness | **Enforced for agents that POST check-ins** | `POST /heartbeat/{agent}` records `last_seen`; `GET /liveness` lists stale vs live (frozen-clock test). Stale means **no check-in in the window, NOT evidence the process is dead**; no agent checks in on either estate until the SDK and the skills redeploy |
| A killed agent's *in-flight* process stops | **Declared only** (unchanged by the endpoint call — calling an endpoint is not the process halting) | v0.1 has no process supervisor; the agent stops at its next check/heartbeat. A rogue runtime that ignores both is contained by revoking tokens + the sentinel, not by SIGKILL. The one exception is the X3 canary's own process, whose work loop stops on the signal (`packages/field-agent` tests): it proves the signal path end to end, not that any business agent complies |
| A retire cannot be undone from here | **Enforced in code** | all four status-writing routes are guarded: `/kill` answers **409** instead of flipping `retired`→`killed`, `/revive` answers **409** instead of putting a decommissioned agent back to `active`, `/kill/domain` skips them into `skipped_retired`, and `/drill` answers **409** because a drill flips the record to `killed` and its restore is allowed to fail — leaving a record `/revive` would then accept. Adversarial tests for each, plus the two laundering chains end to end (kill-then-revive, drill-then-revive) and the positive cases that keep the guard about `retired` rather than about the route |
| Operator is authorized (`authorized_operators` in manifest) | **Declared only** | operator is a recorded string; authn is out of v0.1 scope |

## LIMITS

- **Deliberate asymmetry:** authority creation (delegation mint) is
  ledger-first fail-closed; authority destruction (kill) is act-first with
  best-effort logging. A halt must never be delayed by an audit outage.
  Consequence: a kill during a ledger outage is visible only in the
  registry's `updated_at` and the missing `kill.agent` event.
- Kill latency to *effect* depends on the agent's check/heartbeat cadence;
  the drill measures platform-side propagation, not agent-side compliance.
- **The endpoint call is a signal, not a stop.** `outcome: called` means the
  agent's endpoint answered, nothing more. What the agent does with it is the
  agent's business; the enforceable halt remains the registry flip that the
  sentinel reads on every check. The "in-flight process stops" row above
  stays **Declared only** for exactly this reason.
- **A drill on an allowlisted estate sends a REAL halt signal.** `/drill`
  performs a real kill and, when the host is allowlisted, really calls the
  agent's endpoint. On an estate where `FIELD_KILL_ENDPOINT_ALLOWLIST` names
  live agent hosts, a "drill" is a live halt signal to those agents. The
  registry status is restored; the signal cannot be.
- **Domain kills are serial.** Worst case: N agents x 2 s endpoint timeout.
  `killswitch domain` uses a 30 s client timeout, so roughly 14 agents with
  unreachable endpoints can outlive the CLI call even though the server
  finishes the halt. Larger estates should kill per agent or raise the
  client timeout.
- **The allowlist gates the HOST, not the path or the method.** Naming a
  host there permits any path and any method the manifest declares on it.
  It is an egress boundary for this service, not an authorization check on
  the agent's endpoint — the agent still has to authenticate the caller
  itself.
- **The kill reason leaves this service (X3).** It travels to every
  allowlisted agent endpoint in `x-field-kill-reason` (first 512 characters),
  over plain HTTP on the compose network. It was already ledger text; do not
  put anything in a kill reason that the agent's host must not see.
- **Liveness is check-in evidence, not process evidence.** `last_seen: null`
  counts as stale, and nothing on either estate POSTs a check-in today, so
  every agent reads stale until the SDK and the skills redeploy. A stale row
  is a prompt to investigate, never a finding that a process is dead; a live
  row is only evidence that something POSTed with that agent id.
- The heartbeat store is a local SQLite file, not replicated. A wiped
  `$FIELD_DATA_DIR` makes every agent look stale until its next check-in.
- **Estate reality (2026-09-12).** Both estates run pre-v1.2 images. Until
  Don redeploys, `POST /heartbeat/{agent}` and `GET /liveness` do not exist
  there and `FIELD_KILL_ENDPOINT_ALLOWLIST` is unset, so everything in this
  file marked "Enforced in code" for v1.2 is test- and CI-proven only and the
  estate status of each is **Declared**.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
