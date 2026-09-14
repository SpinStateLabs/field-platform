# SPEC — spend-governor

**Purpose:** Meter spend events (cents, tokens, actions) per agent against
manifest-derived caps. Crossing a configurable threshold (default 80%)
creates an escalation in a human queue *before* the cap; reaching the cap
flips state to BLOCK, which the conformance-sentinel enforces.

**Exec owners:** CFO / CTO.

**FIELD letter:** E — Enforcement.

**v0.1 scope**
- SQLite store: caps, spend events, escalation queue.
- Integer-only arithmetic (money = cents); threshold check is
  `spent*100 >= limit*pct` — exact, no floats.
- `SpendCapConfig.from_manifest` maps the manifest's `enforcement.spend_cap`
  (sub-cent limits refused loudly).
- FastAPI: `/caps`, `/spend`, `/status/{agent}`, `/escalations` (+resolve),
  `/health`. Ledger notes best-effort (`spend.recorded`, `spend.escalate`,
  `spend.cap_reached`, `spend.escalation_resolved`).
- At most one OPEN escalation per (agent, kind): checked and inserted in one
  store call, so concurrent threshold crossings open and ledger one.
- Resolve: first resolver wins. 200 for the resolving call and for the same
  human retrying (unchanged row, no second note); 409 with the unchanged row
  for a different human.
- CLI: `governor set-cap | spend | status | rate-limits | escalations | resolve | serve`.
- Adversarial tests: negative spend rejected; integer boundary exactness at
  99% of a $6,000 cap.
- D1 throttle: `rate_limits` table + `PUT/GET /rate-limits/{agent}` loaded by
  `set-cap --from-manifest`; rolling windows over the period grammar
  `hourly|daily|monthly|<N>s|m|h|d`; `session` recorded declared-unenforced;
  `SpendState.THROTTLED` with `retry_after_seconds` and `throttled{…}`;
  `GET /status/{agent}?action=`; precedence BLOCK > THROTTLED > ESCALATE >
  OK; the usage policy's token window throttles too.
- D1 metering (options A + B adopted): `spend.action` / `spend.source`
  (migration at open); `source=sentinel` rows from the sentinel's metered
  ALLOWs; per-action counting max(self, metered); `GET /totals/{agent}?since=`
  (with the cap's `currency`) for the sentinel's USD token spend ceiling
  (D1e). Clock seam `create_app(clock=)`. `spend_governor.provisioning`:
  the one manifest rate-limit loader (validate before any PUT, load after
  the cap PUT) — used by `set-cap --from-manifest` and by lifecycle-manager's
  `provision`.
- D1f: an unsupported `spend_cap.period` (`per-run`) raises
  `UnsupportedCapPeriodError` — never metered as `total`.

**Explicit non-goals (v0.1)**
- No spend interception — metering is self-reported (decorator/gateway wire
  it in later phases), plus the sentinel's count of the ALLOWs it answered.
- No currency conversion; one currency per cap.
- No `per-run` window semantics (refused).
- No in-line refusal (no 429): THROTTLED is a state the sentinel enforces.
- No LLM anywhere.
