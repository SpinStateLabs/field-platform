# spend-governor

Deterministic spend metering against manifest caps. FIELD letter **E**
(Enforcement). Exec owners: **CFO / CTO**.

The meter, not the gate: it records spend (cents, tokens, actions), fires a
**human escalation before the cap** (default 80%), reports `BLOCK` at
the cap and `THROTTLED` (with `retry_after_seconds`) when a rate window is
exhausted. The conformance-sentinel reads `/status` and refuses the action.
Nothing here answers 429 or blocks in-line. All arithmetic is integer —
money is cents, comparisons are exact, no LLM.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/caps/{agent_id}` | PUT / GET | Configure caps (from a manifest's `spend_cap` or explicit) |
| `/rate-limits/{agent_id}` | PUT / GET | The agent's `enforcement.rate_limits` set (PUT replaces it; needs a cap first, else 404; unknown periods 422). Each row reads `enforced` or `declared_unenforced` |
| `/spend` | POST | Record a spend event → returns status (OK / ESCALATE / THROTTLED / BLOCK). Optional `action` attributes the row to one action; `source` is `self` (default) or `sentinel` (one metered ALLOW, must name the action) |
| `/totals/{agent_id}?since=ISO` | GET | Recorded cents + priced token cost since an instant, with the cap's `currency` (the sentinel's USD token spend ceiling, D1e) |
| `/usage` | POST | **Agents report token usage** (`model`, `input_tokens`, `output_tokens`); FIELD prices it from the model and folds cost into the cap, runs rogue detection |
| `/usage/{agent_id}` | GET | Token totals, computed cost, per-model breakdown, open rogue flags |
| `/policies/{agent_id}` | PUT / GET | Usage policy: `allowed_models` allow-list + `token_rate_limit` burst ceiling |
| `/status/{agent_id}[?action=A]` | GET | Current window totals + state (the sentinel reads this, passing the checked action). `spent_actions_self` / `spent_actions_metered` show both counts; `throttled{kind,action,count,max,period,period_seconds}` and `retry_after_seconds` are set only when THROTTLED |
| `/escalations` | GET | Open human-review queue |
| `/escalations/{id}/resolve` | POST | Human resolves (`resolved_by` required). **First resolver wins**: 200 with the row; the same human retrying gets 200 and the unchanged row; a different human gets **409** with the unchanged row (the first `resolved_by` is never overwritten) |
| `/health` | GET | Liveness |

## Token-cost governance

Agents must **report token usage** (self-report via `/usage`, or
automatically through `force-gateway`, which now sends model + tokens).
FIELD computes the **dollar cost from the tokens and the model used** via a
price book (`field_core.pricing`) and feeds that cost into the *same* cap
that already escalates-before-cap and blocks — so runaway token spend trips
the existing machinery. On top of the cap, three deterministic **rogue
signals** make abuse visible even below it:

| Signal | Fires when | Ledger event |
|---|---|---|
| `rogue_model` | the agent uses a model outside its `allowed_models` allow-list | `usage.rogue_model` |
| `rogue_burst` | input+output tokens in the rate window ≥ `token_rate_limit` | `usage.rogue_burst` |
| `unpriced` | the model has no price — cost can't be governed (suspicious in itself) | `usage.unpriced` |

Each finding is a ledger event **and** a human-queue escalation. The
default price book is Anthropic's **public list price**, transcribed from
platform.claude.com on a dated snapshot and **fully overridable** with your
negotiated rates (`FIELD_PRICE_BOOK` → a JSON file). Money is integer
price units (1e-7 USD) end-to-end; no floats near a limit.

## Throttle (D1)

`governor set-cap --from-manifest` also loads `enforcement.rate_limits`
into the `rate_limits` table (a separate table and endpoint, so
`SpendCapConfig` stays `extra='forbid'` for every caller). Everything is
validated before the first PUT; a refusal configures nothing. The loader is
`spend_governor.provisioning` (`rate_limits_from_manifest` before any PUT,
`load_rate_limits` after the cap PUT), shared by both manifest-driven
provisioning paths: `governor set-cap --from-manifest` and `lifecycle
provision` (validate -> register -> cap -> rate limits -> mint; also behind
`tools/provision_ssl_agents.py`). A hand-written `PUT /caps` (the SDK's
`examples/04_bootstrap_operator.py`, raw REST) loads no rate limits.

- **Period grammar** (exact strings): `hourly` (3600 s), `daily` (86400 s),
  `monthly` (30 days), `<N>s|<N>m|<N>h|<N>d` (up to 366 days). Every window is
  ROLLING — `ts > now − period` — unlike the cap's UTC calendar windows.
  Anything else is refused (422 / CLI exit 1).
- **`session`** (the templates' `tool_call` budget for the Claude Code
  Enforcement Gate) has no server-side meaning: it is stored
  `declared_unenforced`, ledgered `spend.rate_limit_declared_unenforced`,
  warned about loudly on stderr, and never throttles. It is never mapped to
  `total`.
- **Matching:** a limit applies when the status request's `action` equals
  the limit's `action` byte for byte. `tool_call` is not a wildcard; case
  and whitespace variants are different actions.
- **Counting (option A, adopted):** rows carry `action` and `source`. One
  action's window counts the sentinel-metered rows for that action when any
  exist in the window, else the self-reported rows. The cap's
  `action_limit` counts, per action, max(self-reported, metered), plus every
  unattributed (`action` NULL) row. `spent_actions_self` and
  `spent_actions_metered` expose both.
- **Token window:** a usage policy's `token_rate_limit` over
  `rate_window_seconds` throttles too (same arithmetic, over `/usage` rows),
  on every status read — for EVERY action, not just the token-spending one.
  The field-agent plugin's `bootstrap_operator.py` template installs
  `token_rate_limit: 200_000` per hour, so every agent bootstrapped from it
  gets this (see LIMITS).
- **State:** THROTTLED when `count >= max`; `retry_after_seconds` = whole
  seconds, rounded up, until enough of the oldest rows leave the window.
  Precedence **BLOCK (cap) > THROTTLED > ESCALATE > OK**. Escalations still
  open off the cap arithmetic underneath, so a throttled spend that crosses
  the threshold still reaches the human queue.
- **Who pauses on THROTTLED:** the sentinel's step 8 (BLOCK `E.rate_limit`).
  Readers that compare `== "BLOCK"` — the sentinel's judge-budget gate and
  force-gateway's self-check — do NOT pause on it (stated, tested for the
  judge gate).

## CLI

```
governor set-cap <agent-id> [--from-manifest m.yaml | --limit-cents N] [--token-limit N] [--action-limit N] [--period daily|monthly|total]
governor spend <agent-id> [--cents N] [--tokens N] [--actions N] [--action A]    # exit 1 on BLOCK
governor status <agent-id> [--action A]
governor rate-limits <agent-id>
governor escalations [--agent-id ID]
governor resolve <escalation-id> --by "Human Name"
governor serve [--port 8006]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Integer arithmetic; no float drift at limit boundaries | **Enforced in code** | cents-int comparisons (`spent*100 >= limit*pct`); adversarial test |
| Threshold escalation fires **before** the cap, once per crossing | **Enforced in code** | dedup on open escalations: the check and the insert are one store call (one lock hold, one `BEGIN IMMEDIATE` transaction), so concurrent crossings open and ledger exactly one escalation per (agent, kind); a partial unique index backs it wherever the database holds no pre-v1.2 duplicates (`tests/test_escalation_atomicity.py`) |
| A resolved escalation keeps its first resolver | **Enforced in code** | `UPDATE … WHERE resolved=0`; exactly one `spend.escalation_resolved` note; retries and refused (409) resolves write none (`tests/test_escalation_atomicity.py`, `tests/test_governor_store_concurrency.py`) |
| At/over cap ⇒ status BLOCK | **Enforced in code** | pure `evaluate()` |
| Negative spend cannot reduce totals | **Enforced in code** | `ge=0` validation |
| Spend without a configured cap is refused | **Enforced in code** | 404 "ungoverned spend" |
| Manifest `spend_cap` maps exactly (sub-cent limits refused) | **Enforced in code** | `from_manifest` |
| Agents actually report their spend | **Declared only** | self-reported metering; interception belongs to force-gateway (LLM spend) and sentinel wiring |
| BLOCK actually stops the agent | **Declared only** (here) | enforcement is the sentinel's `/check` — this service only reports state |
| Status is THROTTLED after N counted actions in a rolling window, with `retry_after_seconds`, for periods the governor can parse; OK again once the oldest rows age out | **Enforced in code** | `_throttle` + `window_retry_after`, integer arithmetic; frozen-clock tests: N allowed, N+1 THROTTLED, `retry_after_seconds` = 1 at T+period−1 s, OK at T+period, token window likewise, cap BLOCK outranks THROTTLED, unlimited action not throttled, case/whitespace variants and `tool_call` never match (`tests/test_throttle.py`). The counts are fed by sentinel-metered ALLOWs, else self-reported per-action rows — the self-reported side carries the row above's caveat; THROTTLED stops nothing here (row above) |
| One action checked AND self-reported is counted once toward the `action_limit` cap, and an action only one side saw is never lost from that count | **Enforced in code** | option A: per-action max(self, metered) for `action_limit`; unattributed rows count toward totals only (`tests/test_throttle.py` option A tests). Rate WINDOWS are different: they prefer metered rows and can under-count self-reports — an agent THROTTLED on 3/2 self-reports reads OK after one sentinel-metered row (`test_window_prefers_metered_rows_while_the_cap_takes_the_max`; LIMITS) |
| `session` rate limits are enforced | **Declared only** (gate-only) | stored `declared_unenforced`, ledgered `spend.rate_limit_declared_unenforced`, loud CLI warning, never throttles (test); the Claude Code Enforcement Gate is what counts a session |
| Unknown rate-limit periods and rate limits without a spend cap are refused | **Enforced in code** | `parse_rate_period` → 422 / CLI exit 1 with nothing configured; `PUT` and `GET /rate-limits` 404 for an uncapped agent; `spend_governor.provisioning` refuses before any PUT and reports a refused load as `failed`, never silently (tests) |
| A manifest's `rate_limits` are loaded by both manifest-driven provisioning paths, `governor set-cap --from-manifest` and `lifecycle provision` | **Enforced in code** | both call `spend_governor.provisioning` (tests here; `services/lifecycle-manager/tests/test_provision_rate_limits.py`: a declared set is loaded after the cap and the window throttles after max, a re-provision without `rate_limits` clears the stale set, an unknown period or duplicate entry raises before any side effect, a governor that refuses the set or is unreachable fails the `rate_limits` step and mints nothing). A hand-written `PUT /caps` (SDK example operator, raw REST) loads none |
| An unsupported `spend_cap.period` (`per-run`) is refused, never metered as `total` | **Enforced in code** | `UnsupportedCapPeriodError` from `SpendCapConfig.from_manifest`; `set-cap --from-manifest` exits 1 naming it and configures nothing (tests) |
| A pre-D1 `spend.sqlite3` (7-column `spend`) opens and keeps its rows | **Enforced in code** | `_migrate_spend_attribution` at open: PRAGMA → ALTER; old rows read as `source='self'`, unattributed (`test_old_seven_column_spend_db_migrates_at_open`) |

## LIMITS

- Self-reported spend: an agent that never calls `/spend` never hits the
  cap. The honest deployment wires spend recording into the `@governed`
  decorator and the force-gateway, not the agent's goodwill.
- Ledger notes are best-effort (metering survives ledger outages; the gap
  is visible in audit as missing `spend.*` events). Mint-style fail-closed
  semantics belong to authority changes, not meters.
- Window boundaries are UTC calendar days/months.
- A persisted database that already holds duplicate open escalations
  (written before the check-and-insert was atomic) still opens: it logs a
  warning, skips the unique index, and leaves every duplicate in the queue
  for a human (nothing is auto-resolved). The index is added on the first
  start after they are resolved. The store keeps no `resolved_at` column,
  so the resolution time is not recorded here.
- Rollback: an image older than this change, run against a database that
  already has the index, gets an `IntegrityError` (HTTP 500 on `/spend` or
  `/usage`, after the spend is recorded) instead of a duplicate escalation
  when two requests cross a threshold at the same moment.
- **The D1 migration runs at open.** `GovernorStore.__init__` adds
  `spend.action` and `spend.source` the first time the D1 image STARTS
  against a persisted `spend.sqlite3` — before any request, not at the first
  `/spend` (it also adds the `rate_limits` table, which older images ignore).
  Image rollback is therefore clean only until that first start. After it,
  a pre-D1 image's positional 7-value `INSERT INTO spend VALUES` fails
  ("table spend has 9 columns but 7 values were supplied" — pinned by
  `test_old_seven_column_spend_db_migrates_at_open`): every `/spend` answers
  500 and records nothing. Rolling back past it is a data step: restore the
  pre-deploy copy of `spend.sqlite3` (losing spend recorded since), or, with
  the service stopped, drop the index and then the two columns in this order
  — `DROP INDEX idx_spend_agent_action_ts; ALTER TABLE spend DROP COLUMN
  source; ALTER TABLE spend DROP COLUMN action;` (SQLite ≥ 3.35; dropping
  `action` while the index exists fails) — which keeps the rows but loses
  their attribution: sentinel-metered rows then count as plain actions, so
  the pre-D1 double count returns. Re-deploying D1 re-adds the columns, not
  the lost labels. (That
  sequence was run once against a scratch database, 2026-09-13; it is not a
  test.)
- **The throttle is not atomic.** The sentinel reads `/status` and posts the
  metered row in separate calls, so concurrent checks of one action can each
  see `count < max` and overshoot by the number in flight.
- **Option A's window rule can under-count self-reports.** Once any
  sentinel-metered row for an action is in the window, that action's
  self-reported rows are ignored there: an agent that checks once and
  self-reports 3 counts 1 toward the window (the cap's `action_limit` takes
  max = 3). Callers that go through the sentinel should report cents only
  (option B).
- **`source=sentinel` is a label, not an identity.** Any caller holding the
  shared secret can post it; per-service authorship is Phase F2b.
  Sentinel-metered rows are not re-ledgered as `spend.recorded` — the
  `conformance.allow` (or `conformance.shadow_*`) event that caused each row
  is its ledger record; a failed post is ledgered by the sentinel as
  `sentinel.metering_gap`.
- `monthly` in a rate limit is a rolling 30 days, not a calendar month.
  Rate windows are rolling; cap windows are UTC calendar days/months.
- **A token burst now BLOCKs every checked action until the window ages
  out.** Any agent with a usage policy `token_rate_limit` reads THROTTLED on
  every `/status` while its token window is exhausted, so an enforcing
  sentinel BLOCKs all of its checked actions `E.rate_limit` (with
  `retry_after_seconds`). Before D1 the burst's open `rogue_burst`
  escalation ESCALATEd those checks instead, and a human resolving it
  unblocked the agent at once; now resolving it does not lift the BLOCK —
  only the window ageing out does (sentinel
  `test_an_agents_token_burst_blocks_every_checked_action`). The plugin
  template `plugins/field-agent/templates/bootstrap_operator.py` sets
  `token_rate_limit: 200_000` / hour for every agent it bootstraps — check
  the estates' policies before flipping the sentinel to enforce.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
