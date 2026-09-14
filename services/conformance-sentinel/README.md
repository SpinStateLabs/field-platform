# conformance-sentinel

The policy-enforcement point. Every proposed action is checked against the
agent's manifest, token, spend state, and kill status — and answered
**ALLOW / BLOCK / ESCALATE with the failed clause id**. FIELD letter **E**
(Enforcement). Exec owner: **CISO**.

This is the service that turns FIELD from *declared* into *enforced*.

## Decision sequence (first failing clause decides)

| # | Check | Clause on failure |
|---|---|---|
| 1 | Sealed ledger reachable (no audit ⇒ no action) | `L.unreachable` BLOCK |
| 2 | Agent registered & active (killed ⇒ instant block) | `R.unregistered` / `E.kill_switch` BLOCK |
| 3 | Manifest present & valid (`field validate`) | `I.manifest` BLOCK |
| 4 | Token presented, active, bound to this agent | `D.token` / `D.expired` / `D.revoked` BLOCK |
| 5 | Action in **both** token scope and manifest scope | `D.scope` BLOCK |
| 6 | Irreversible-action policy | `E.irreversible` BLOCK or ESCALATE |
| 7 | Declared escalation triggers (substring match) | `E.escalation_trigger` ESCALATE |
| 8 | Spend state from the governor for THIS action (`/status/{agent}?action=`): cap, token spend ceiling (D1e), rate window, threshold | `E.spend_cap` BLOCK / `E.rate_limit` BLOCK (with `retry_after_seconds`) / `E.spend_threshold` ESCALATE |

Every verdict (including ALLOW) is written to the sealed ledger as
`conformance.allow|block|escalate`.

## Throttle and metering (D1, options A + B adopted)

- **THROTTLED ⇒ BLOCK `E.rate_limit`.** Step 8 asks the governor for the
  checked action's status. Precedence: cap BLOCK (`E.spend_cap`) > the
  token's spend ceiling (`E.spend_cap`) > THROTTLED (`E.rate_limit`) >
  ESCALATE (`E.spend_threshold`). The BLOCK carries
  `context.retry_after_seconds`, also written into the ledger payload (and
  into the shadow verdict and `conformance.shadow_block` payload in
  log-only). `ActionBlocked.retry_after` reads it.
- **Every ALLOW is metered, in either mode (option A).** After the verdict
  is built and ledgered, the sentinel posts `actions=1, action=<req.action>,
  source=sentinel, shadowed=<bool>` to the governor for every response it
  returns as ALLOW — a log-only shadow still ran, so its window must fill
  for `would_block: E.rate_limit` to be observable. That includes a
  log-only shadow decided at steps 1–4 (ledger, registry, manifest, token),
  where the caller never proved it is `agent_id`: the row is counted
  against the agent it NAMED (Don's decision 2026-09-13; the cost is in
  LIMITS). Never on BLOCK or ESCALATE. The verdict context says
  `metered: true`, or `metered: false` with `reason: no_cap` (step 8 read no
  cap, so nothing is posted; or the governor 404'd a shadow decided before
  step 8 — an unregistered agent's included) or `reason: metering_gap` (any
  reply but 201 — a pre-D1 governor's 422 included: ledgered
  `sentinel.metering_gap`, the verdict is NOT flipped).
- **The judge-budget gate is unchanged.** It still reads the sentinel's own
  status with one positional argument and pauses only on `== "BLOCK"`:
  THROTTLED does not pause judgments (test).
- **Token spend ceiling (D1e).** When introspection carries
  `max_spend_usd`, the agent's governor-metered spend since the token's
  `issued_at` (`GET /totals`) at or over it BLOCKs `E.spend_cap` (context
  `token_max_spend_cents`, `token_spent_cents`); an unreadable ceiling, an
  unverifiable total, or a total in any currency but USD (the cap's
  `currency`, from `/totals`) BLOCKs; no cap at all ESCALATEs.
  delegation-authority stamps the value from the DOA roster row matched at
  mint and returns it with `issued_at` on `/introspect` (v1.2 D1e), so a
  token minted with the roster unset, or under a row without
  `max_spend_usd`, carries no ceiling.

## Operating mode — safe-by-default (ADR 02)

`FIELD_SENTINEL_MODE` sets the estate-wide posture; one env var flips it:

| Mode | Behavior |
|---|---|
| `log_only` (**served default**) | Verdicts are computed and **shadow-ledgered** as `conformance.shadow_block` / `shadow_escalate` (carrying the `would_block` clause), but `/check` returns **ALLOW** — nothing is blocked. A new estate observes before it enforces. |
| `enforce` | Verdicts block/escalate for real (the sequence above). |

A new estate ships in `log_only` and graduates to `enforce` only after the
measured gate (catch ≥ 95%, false-block ≤ 2% — see `tasks/todo.md`). Demos and
the compose smoke set `FIELD_SENTINEL_MODE=enforce` to showcase enforcement.
`GET /health` reports the active mode.

## Semantic judge (S3 / ADR 02) — flagged, default OFF

`FIELD_SENTINEL_JUDGE = off (default) | mock | anthropic`. With the flag unset
the engine is behaviorally identical to the structural sentinel (exact-match
scope, hard-block). When enabled, an action that fails exact membership AND
fires `routing.needs_semantic_judgment` is judged against the **effective
scope (token∩manifest — the narrower grant still wins)**:

- **Fail-to-escalate everywhere:** injection-screen trip, upstream error,
  unparseable/uncertain verdict, confidence below the floor
  (`FIELD_JUDGE_CONFIDENCE_FLOOR`, default 0.8), governor unreachable, no
  sentinel cap, or budget exhausted → **ESCALATE `D.semantic`** — never
  silent-allow, never silent-block.
- **Spend-metered:** every judgment posts to the governor's `/usage` against
  the sentinel's own cap; no cap or cap BLOCK ⇒ structural-only throttle
  (ESCALATE). Unmeterable judgments escalate — no unmetered LLM calls.
- **Version-pinned:** `FIELD_JUDGE_MODEL` (default `claude-sonnet-5`);
  the model id is recorded in every verdict reason and `sentinel.judge`
  ledger telemetry event.
- A judge pass does NOT bypass the remaining checks (triggers, irreversible
  policy, spend state still run). Judge verdicts flow through the operating
  mode like everything else — log-only shadows them.
- **Routing (v1.2 D2e):** the judge's base URL is `FORCE_GATEWAY_URL` >
  `ANTHROPIC_BASE_URL` > `https://api.anthropic.com` (`field_core.llm`).
  Toward `FORCE_GATEWAY_URL` every judge call carries
  `x-force-passthrough: judge` (forwarded uninstrumented; platform judge
  traffic is not hygiene telemetry) and `x-field-auth` when
  `FIELD_SHARED_SECRET` is set; the secret is never sent to
  `ANTHROPIC_BASE_URL`. The sentinel still needs `ANTHROPIC_API_KEY` in its
  own env to construct the judge; routed through the gateway, forcegw's key
  is the one used upstream. Compose no longer passes `--mock` to forcegw
  (D2), so until `ANTHROPIC_API_KEY` is placed for forcegw (the GB10 `.env`
  and a Fly secret — Don's step; no key is in the repo) the gateway answers
  `POST /v1/messages` with 502, and on a judge-on estate every judgment
  fails to escalate (`D.semantic`). Routing is tested in
  `services/force-gateway/tests/test_d2_llm_callers.py`; scoring against the
  real model stays Declared-untested.

## Self-governance (S4 / ADR 02) — who guards the guard

The Sentinel is governed by the instrument it enforces. Its own FIELD
manifest ships in the package (`self_manifest.yaml`; inspect with
`sentinel self-manifest` — exit 1 if it ever fails validation):

- **Named owner:** `identity.principal = "Founder & CTO, Spin State Labs"`.
- **Read-only grounding:** the delegation scope contains only
  read/evaluate/append/invoke entries — the Sentinel is never delegated the
  power to modify manifests or its own policy (test enforces the verb
  restriction). Concretely tested: the API surface has no PUT/PATCH/DELETE
  and POST exists only at `/check`; a full check battery leaves manifest
  files byte-identical.
- **Judge budget from the manifest:** `enforcement.spend_cap` (USD 5 daily)
  is the S3 semantic-judge budget; apply it with
  `governor set-cap conformance-sentinel --from-manifest <path>` — a test
  proves a judged call is allowed and metered against the manifest-derived
  cap, and the S3 spend gate already refuses unmetered judgments.
- **Tenant isolation (tested):** agent A's `/check` resolves ONLY A's
  `manifest_ref` (resolver-spy test), and with the judge on, the judged
  scope contains only entries from A's own manifest — another agent's
  grants can never leak into A's verdict or the judge prompt.
- **Who stops the stopper:** one env var (`FIELD_SENTINEL_MODE=log_only`)
  reverts the estate to observation; registration/cap/kill remain
  operator-side tools the Sentinel cannot invoke on itself.

## Seeded-violation scorecard (S2 / ADR 02)

`sentinel score` runs a deterministic 100-action seeded suite against a
**log-only** estate (it refuses anything else) and emits a sourced scorecard
(`--out-md/--out-json`; exit 0 gates pass, 3 gates fail). Categories:
scope-breach, expired-token, revoked-token, ledger-unreachable,
ambiguous-violating, exact-conforming, ambiguous-conforming. Gated metrics
*(proposed; ratified at PoC exit)*: **gated catch ≥ 95%** (would-be verdict
must match the seed's expected clause AND decision — refusals for the wrong
reason don't count) and **seeded structural false-block ≤ 2%**. Also reported,
not gated: combined false-block including the semantic gap (paraphrased
conforming actions hard-block pre-S3), false-escalate rate, routing-predicate
coverage (`routing.needs_semantic_judgment` — measurement-only until S3
attaches the judge to it), would-have-blocked, tokens/judgment (0 until S3).

The seeded suite is a **regression harness, not an adversarial eval**: seeds
are authored against the same exact-match checks they exercise, so the gated
numbers are near-tautological by construction — they verify plumbing. The
binding gates for enforce-by-default remain live (2-week log-only burn-in;
30-day live false-block). Captured run: `score_demo.sh` →
`docs/capstone-evidence/sentinel-scorecard-s2.md|.json`.

## API & CLI

`POST /check` `{agent_id, action, token_id?, irreversible?}` → verdict ·
`GET /clauses` · `GET /health`

```
sentinel check <agent-id> "<action>" [--token-id T] [--irreversible]   # exit 0/2/1 = ALLOW/ESCALATE/BLOCK
sentinel clauses
sentinel serve [--port 8004]
```

## `@governed` — one decorator to govern any Python tool call

```python
from conformance_sentinel.governed import governed, ActionBlocked

@governed(agent_id="invoicing-agent", action="draft invoices",
          token_id=lambda: current_token())
def draft_invoice(row): ...
```

BLOCK raises `ActionBlocked` *before* the function body runs; ESCALATE
raises `ActionEscalated`; sentinel unreachable fails closed.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Killed agents fail their next check instantly | **Enforced in code** | registry read per check; test proves it |
| Out-of-scope actions blocked with `D.scope` | **Enforced in code** | intersection of token + manifest scope; narrower grant wins (test) |
| Expired/revoked tokens blocked with exact clause | **Enforced in code** | live introspection per check |
| Invalid/missing manifest ⇒ all authority lost | **Enforced in code** | adversarial test edits the manifest on disk |
| No ledger ⇒ no actions | **Enforced in code** | reachability gate before any ALLOW |
| Declared-but-unmetered spend caps go to a human | **Enforced in code** | `E.spend_cap` ESCALATE on metering gap |
| An exhausted rate window for the checked action BLOCKs `E.rate_limit` with `retry_after_seconds` in the context and the ledger payload; log-only shadows it; other actions are unaffected | **Enforced in code** | step 8 `THROTTLED` mapping; `tests/test_throttle_metering.py` (frozen-clock governor: N ALLOW, N+1 BLOCK with 3600, 1 at T+3599 s, ALLOW at T+3600 s; shadow `would_block: E.rate_limit`; per-action isolation; cap outranks) |
| EVERY ALLOW in EITHER mode is metered to the governor exactly once — including a log-only shadow decided at steps 1–4, before identity is established; BLOCK/ESCALATE never; an uncapped agent is not posted; any non-201 reply (a pre-D1 governor's 422 included) is ledgered as a gap and never flips the verdict | **Enforced in code** | `SentinelEngine._meter` + `SpendStatusClient.record_action`; tests: one ALLOW ⇒ `spent_actions_metered` +1 and self +0; log-only shadows at step 1 (ledger down), step 2 (killed record), step 3 (manifest gone), step 4 (no token ×3, another agent's token) and step 5 (D.scope) each ⇒ `metered: true` and +1 on the named agent (a max-2 window reads THROTTLED after 3); an unregistered agent's step-2 shadow is posted and its 404 reads `no_cap`; no post and `reason: no_cap` for an uncapped agent at step 8; a real pre-D1 `extra='forbid'` 422 and a 500 through the real client ⇒ `metering_gap` on every ALLOW, one `sentinel.metering_gap` each (`tests/test_throttle_metering.py`) |
| A token's `max_spend_usd` bounds spend under it (`E.spend_cap`) — sentinel half | **Enforced in code** | `_token_ceiling` over `GET /totals?since=issued_at`; tests override the two fields on the real introspection result (frozen governor clock, values no roster can hold): at the ceiling BLOCK, spend before `issued_at` not counted, sub-cent ceilings floor, unreadable ceiling / unverifiable total BLOCK, a CAD cap (or a total naming no currency) BLOCK, no cap ESCALATE |
| A token's `max_spend_usd` is enforced end to end (v1.2 D1e) | **Enforced in code when `FIELD_DOA_ROSTER` is set** (CI-proven; not yet live on an estate) | no override: a roster row with `max_spend_usd: 1.0` is stamped at mint by the real delegation-authority, its `/introspect` returns it with `issued_at`, 99 cents since issue ALLOWs, the 100th cent BLOCKs `E.spend_cap` (`token_max_spend_cents` 100), 5,000 cents recorded before issue do not count, and a token minted with the roster unset is not bounded (`test_a_rostered_tokens_max_spend_usd_blocks_spend_cap_end_to_end`; stamping and storage in `services/delegation-authority/tests/test_d1e_token_ceiling.py`) |
| Blocks/escalates are ledger events | **Enforced in code** | `conformance.*` events |
| Safe-by-default: served estate observes before it enforces | **Enforced in code** | `FIELD_SENTINEL_MODE` defaults to `log_only`; would-blocks are shadow-ledgered, caller not blocked (tests) |
| Scorecard gates: gated catch ≥ 95%, structural false-block ≤ 2% on the seeded suite | **Enforced in code** | `test_scorecard.py` gate test (in-process, full 100-seed corpus) + committed artifact from a real served run |
| Judge control flow: fail-to-escalate on screen trip / error / uncertainty / unmetered spend; narrower grant wins; no check bypass | **Enforced in code** | `test_judge.py` — 7 adversarial escalate paths + intersection + no-bypass tests against the deterministic mock |
| Judge default OFF; a typo in the flag cannot enable an LLM in the loop | **Enforced in code** | `resolve_judge` unrecognized → off (test) |
| Semantic understanding quality (real model judges correctly) | **Declared only** | mock tests prove control flow, not judgment; pending live golden-set evals with the pinned model (`FIELD_JUDGE_MODEL`) |
| Governed by its own instrument: valid self-manifest, CTO owner, judge budget declared there | **Enforced in code** | validation + verb-restriction tests; manifest-derived cap meters a judged call (test) |
| Cannot modify manifests or its own policy over its API | **Enforced in code** | no mutating route, POST only /check; check battery leaves manifest bytes identical (tests) |
| Tenant isolation: agent A's check never reads agent B's manifest | **Enforced in code** | resolver-spy + judge-scope leak tests |
| OS-level manifest immutability | **Declared only** | process behavior is tested. GB10 (v1.2 Phase C, configuration not yet deployed): `integration/demo/docker-compose.gb10.yml` mounts the `field-manifests` volume read-only at `/data/manifests` into every platform service, written only by the one-shot `manifests-admin`; CI job `compose-upgrade-smoke` asserts the `ro` mount and an EROFS write refusal inside each container, and has NOT run yet. What that covers is the FILES in `/data/manifests`: `manifest_ref` is not confined to that directory (an absolute ref or `..` resolves anywhere, and the registry allows PATCHing `manifest_ref`), and every service keeps `field-data` at `/data` read-write, so a manifest written elsewhere on `/data` and registered by ref is still honoured. Fly: a true limit, one container on one volume — the (b) row in `integration/fly/README.md`. Nothing stops root on either host |
| Agents route their actions through `/check` at all | **Declared only** | the sentinel governs what it is asked about; bypassing it is an architecture violation the registry/discovery + gateway layers exist to catch |
| Escalation triggers understand meaning | **Declared only** | v0.1 matching is bidirectional substring — deterministic, not semantic |

## LIMITS

- **Log-only + ledger down loses the observation.** In `log_only`, a
  would-block is shadow-ledgered; if the ledger is unreachable at that moment
  the shadow record is lost and the caller is (correctly) not blocked. The
  scorecard's ledger-unreachable seeds quantify this class; live shadow
  traffic lost during an outage is unrecoverable.
- **Missing-write detection is not implemented.** The ledger check is a
  pre-execution reachability proxy; post-hoc executed-vs-ledgered
  reconciliation (the ADR's "missing ledger writes" class) does not exist and
  is not tested — the scorecard category is named `ledger-unreachable`
  accordingly.
- **Unrecognized `FIELD_SENTINEL_MODE` values silently fall back to
  `log_only`.** Fail-safe direction, but a typo ("enfroce", "true") quietly
  disables enforcement — verify `GET /health` after any mode change (it also
  reports the judge state).
- **The injection screen is pattern-based and evolving.** A screen pass is
  a necessary condition to consult the judge, never proof of a benign
  payload; ADR 02's residual risk (a novel injection with a confident wrong
  verdict) stands — mitigated by log-only burn-in and the fail-to-escalate
  posture, not eliminated.
- **The real Anthropic judge path is Declared-untested.** Tests exercise the
  deterministic mock only; the `anthropic` upstream requires
  `ANTHROPIC_API_KEY` and has no automated coverage until live golden-set
  evals run.
- **Read-only grounding is process behavior, not OS enforcement.** The
  Sentinel ships no code path that writes manifests and its API has no
  mutating surface (tested), but nothing stops another process on the same
  box. Real deployments should mount manifest directories read-only to the
  Sentinel's user.
- **Downstream shadow awareness is S2-R-deep only.** attestation-reporter
  counts shadow verdicts in the conformance rate (own labeled rows),
  compliance-crosswalk labels enforced vs shadow escalation evidence, and
  incident-replay treats `conformance.shadow_block` / `shadow_escalate` as
  failures (clause from `would_block`, labeled "log-only, not enforced") — but
  any OTHER consumer of `conformance.*` events must remember that in
  log-only estates violations appear only as `conformance.shadow_*`.
- **The perimeter is cooperative in v0.1.** `@governed` and the demo agent
  route through `/check`; a malicious process with direct tool access
  simply doesn't ask. Containment for that case = revoked tokens + killed
  status + (later) network-level interception via force-gateway.
- Verdict ledger writes after the reachability gate are best-effort; a
  mid-check ledger crash can lose one verdict event while the action
  proceeds. The gate bounds the window; it does not eliminate it.
- Trigger matching is naive substring; write triggers accordingly
  ("send invoice", not "any external send").
- **The throttle is read-then-post, not atomic.** Concurrent checks of one
  action can all read `count < max` before any metered row lands and
  overshoot by the number in flight. The metering post is synchronous (adds
  one governor round trip, bounded by the client's 5 s timeout, to every
  ALLOW).
- **Deploy the governor with (or before) the sentinel.** A pre-D1 governor
  refuses the metering post's `action`/`source`/`shadowed` keys (422), so a
  D1 sentinel in front of it ALLOWs as before but ledgers a
  `sentinel.metering_gap` on every ALLOW (pinned with the pre-D1
  `SpendRequest` model through the real client), and its `?action=` is
  ignored (no throttle — a statement about the old image, not tested here).
- **In log-only, an unauthenticated caller can fill another agent's
  windows.** Every ALLOW is metered, and a shadow decided at steps 1–4
  (no/expired/revoked token, another agent's token, missing manifest,
  killed or inactive agent, ledger down) never proved it is `agent_id`, yet
  its row counts against the agent it named (Don's decision 2026-09-13, the
  plan's "every ALLOW in either mode"). So any caller that can reach
  `/check` can inflate a registered, capped agent's `spent_actions_metered`
  and push its `/status?action=` to THROTTLED without a token; after an
  enforce flip inside that window the victim's genuine checks BLOCK
  `E.rate_limit` until the window ages out. The rows are `shadowed=true`
  and each such call also lands a shadow D.*/R.*/I.*/L.* record, which is
  how an operator tells them apart; the perimeter secret
  (`FIELD_SHARED_SECRET`) limits who can reach `/check` at all. Before an
  enforce flip, look for recent shadow `D.token` records against agents
  that carry rate limits.
- **The token ceiling assumes a USD cap.** `max_spend_usd` is compared only
  against a USD total; there is no FX, so an agent capped in any other
  currency whose token carries `max_spend_usd` is BLOCKed on every step-8
  check until the cap or the token changes.
- **Metering counts ALLOWs, not completed work.** An ALLOWed action the
  agent then abandons is still counted; an agent that never asks is never
  counted (cooperative perimeter).
- **Judge-affirmed paraphrases on judge-on estates are metered under the
  paraphrase string**, not the scope entry the judge matched, so they never
  count against a limit keyed on the exact scope entry.
- TOCTOU: a kill or revocation landing mid-flight (after ALLOW, before the
  tool completes) is not interrupted — next check catches it.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
