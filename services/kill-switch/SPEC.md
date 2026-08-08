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

**Explicit non-goals (v0.1)**
- No process-level termination (no PIDs, no container stops) — propagation
  is via sentinel checks and heartbeat polls.
- No operator authentication/authorization (recorded, not verified).
- No auto-kill policies (lifecycle-manager, Phase 4, may add an opt-in flag).
