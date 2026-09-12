# SPEC — kill-switch

**Purpose:** Halt an agent (or an entire domain) with one authenticated-human
command, propagate through the registry so the sentinel blocks instantly,
give agents a heartbeat to poll, and prove readiness with timed drills.

**Exec owners:** CEO / CISO.

**FIELD letter:** E — Enforcement.

**v0.1 scope**
- `/kill/{agent}`, `/kill/domain/{domain}`, `/revive/{agent}`,
  `/heartbeat/{agent}` (fail-closed for unknown agents), `/drill/{agent}`
  (kill → verify registry + heartbeat → restore, all timed, ledger events).
- Act-first ordering: kill before ledger, best-effort logging (documented
  asymmetry vs. delegation-authority's ledger-first mint).
- CLI: `killswitch agent | domain | drill | heartbeat | revive | serve`
  (binary named to avoid the shell builtin `kill`).
- Adversarial tests: registry-down kill fails loud (502); unknown-agent
  heartbeat says stop; ledger-down kill still succeeds; drill restores.

**v1.2 additions**
- **Agent-side halt signal.** After the registry flip, `_kill_one` resolves
  the record's `manifest_ref` (`field_core.clients.resolve_manifest_detail`)
  and best-effort calls `enforcement.kill_switch.endpoint` with
  `.method`, 2 s timeout, via an injectable `endpoint_client` seam.
  `KillReport.endpoint_result` carries
  `EndpointResult{outcome: called|failed|skipped, reason, endpoint_host,
  method, http_status, elapsed_ms, error}`; ledger events
  `kill.endpoint_called` / `kill.endpoint_failed` / `kill.endpoint_skipped`.
  Skip reasons: `allowlist_unset`, `host_not_allowlisted`,
  `non_http_endpoint`, `unsupported_method`, `self_endpoint`,
  `no_manifest_ref`, `manifest_unresolved`. The URL is never echoed — the
  parsed host is the only part that leaves the function.
- **SSRF guard (mandatory).** `FIELD_KILL_ENDPOINT_ALLOWLIST`
  (comma-separated hosts, read per call); unset or blank means no call is
  made. Host comparison is EXACT on `urlsplit(endpoint).hostname`. Scheme
  must be http or https, which is what a FIELD 1.1.0 `method: file` kill
  switch is refused by.
- **Self-call guard (mandatory, both mechanisms).** The outbound call carries
  `x-field-kill-origin: kill-switch`; an incoming request carrying that
  header never signals onward. Independently, an endpoint path ending in
  `/kill/{agent_id}` or containing `/kill/domain/` is skipped. An idempotent
  re-kill still sends the signal.
- **Domain kill** runs the same per-agent path; `DomainKillReport.results[]`
  carries `DomainAgentResult{agent_id, outcome, previous_status, error,
  endpoint_result}`. A per-agent registry fault is recorded, not raised, and
  the route stays 200. Serial bound: N agents x 2 s against the CLI's 30 s.
- **Drill** wraps the flip in `try/finally` so no exception can leave the
  agent killed; the restore is itself guarded (`restored: false` + ledger
  `kill.drill.restore_failed` rather than masking the original error).
  `DrillReport` gains `endpoint_confirmed_ms: float | None` and
  `endpoint_result`.
- **Heartbeat store.** `kill_switch/store.py` `HeartbeatStore` (SQLite,
  registry-store pattern, explicit `close()`) at
  `$FIELD_DATA_DIR/killswitch/heartbeats.sqlite3`;
  `create_app(..., heartbeats=None, clock=None, endpoint_client=None)`.
  `POST /heartbeat/{agent}` records `last_seen` then answers with GET
  semantics (unknown agent still `killed: true`, recorded with status
  `unregistered`). `GET /heartbeat` never writes.
  `GET /liveness?stale_after=SECONDS` lists registry-active agents with no
  check-in inside the window (`last_seen: null` counts as stale) and the
  live ones; tested on an injected clock, never a real sleep.
- **CLI:** `killswitch checkin <id>` (exit 1 if killed) and
  `killswitch liveness --stale-after`. Agent side: `LivenessClient.checkin`,
  `FieldAgent.checkin`, `fieldagent checkin`, plus `Send-FieldCheckin` in
  `tools/field-rest.ps1` and the check-in in the demo agent.

- **Retired agents are protected (B4).** `retired` is terminal: `/kill` and
  `/revive` answer **409**, `/kill/domain` skips them and lists them in
  `skipped_retired` (per-agent outcome `skipped_retired`). Without this a
  kill followed by a revive turns a decommissioned agent back into an
  `active` one. `/drill` is deliberately NOT covered — it restores the
  prior status, so a retirement survives it.

**Explicit non-goals (v0.1 — still true)**
- No process-level termination (no PIDs, no container stops) — propagation
  is via sentinel checks and heartbeat polls. The v1.2 endpoint call is a
  SIGNAL to a cooperating agent, not a stop.
- No operator authentication/authorization (recorded, not verified).
- No auto-kill policies (lifecycle-manager, Phase 4, may add an opt-in flag).
- Liveness does not probe agents. A stale row means no check-in in the
  window, never a finding that a process is dead.
- No retries or queue behind the endpoint call: one attempt, 2 s, recorded.
