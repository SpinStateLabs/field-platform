# lifecycle-manager

Authority hygiene as a scheduled job. Sweeps the registry and
delegation-authority for the three ways agents rot — **expiring
authorities**, **re-attestation due**, and **orphans** (owner not on the
human roster) — escalating each finding to the ledger. FIELD letters
**I + D**. Exec owners: **CIO / CHRO**.

The CHRO is in the loop for a reason: agents get orphaned when *people*
leave. The roster (`owners.csv`) is HR's export, not IT's.

## CLI (the scheduled-job path)

```
lifecycle sweep --roster owners.csv \
  [--expiry-days 30] [--reattest-days 90] \
  [--auto-kill-orphans] [--operator "CHRO quarterly sweep"] \
  [--markdown report.md]
```

Exit 0 = clean, 3 = findings (wire into Task Scheduler / cron; alert on 3).
The sweep also asks the ledger for its retention check (`GET
{FIELD_LEDGER_URL}/retention/check`, C2): a `violation`, `no_estate_policy`,
`unresolvable` or `unavailable` answer — or a ledger that cannot answer — is
reported as `retention_policy` in the report (and a "Retention policy"
section in `--markdown`) and exits 3. It writes no ledger event.
`owners.csv` needs a header with an `owner` column; matching is
case-insensitive on the full owner string.

### `owners.csv` — one row per HUMAN, with optional `aliases`

```csv
owner,aliases
Don Hagell,"Don Hagell, Spin State Labs"
Jane Smith,J. Smith;jsmith@example.com
```

- `owner` is the human. `aliases` (optional) lists the other strings the
  registry records for **the same person**, separated by `;`. An agent whose
  registry `owner` equals the owner **or any alias** is not an orphan.
- Matching is unchanged: case-insensitive, exact after stripping each value.
  No substring, no whitespace folding — `Spin State Labs` does not match
  `Don Hagell, Spin State Labs`.
- Blank alias entries (`;;`, a trailing `;`) are ignored. A row with no owner
  is ignored together with its aliases.
- CSV quoting applies: a value containing a comma must be quoted. An unquoted
  comma is refused by name, and the sweep does not run, in the two shapes that
  can be detected:
  - a row with more fields than the header (`owners.csv line N: more fields
    than the header`) — before v1.2 it crashed on `'list' object has no
    attribute 'strip'`;
  - a value that starts with whitespace (a space, TAB, NBSP, U+3000 or any
    other blank) right after an unquoted comma (`owners.csv line N: a value
    starts with whitespace after an unquoted comma`). `Don Hagell, Spin State Labs` unquoted under `owner,aliases` is
    exactly two fields; unguarded it would read as owner `Don Hagell` plus
    alias `Spin State Labs`.
- **Not detectable:** an unquoted comma with NO whitespace after it that
  yields no more fields than the header. `Don Hagell,Spin State Labs` under
  `owner,aliases` (or under `owner,aliases,team` with the last column left
  off) is owner `Don Hagell` with alias `Spin State Labs` to any CSV reader,
  and is read that way. Quote every value that contains a comma.
- `roster_size` in the report counts humans (owners), not alias strings.
- A roster **without** an `aliases` column behaves exactly as before.

**Aliases are declared by whoever writes the CSV.** Nothing checks that an
alias is the same person as its owner: adding a string as an alias silently
clears every agent recorded under it from the orphan report. Treat an alias
line as an accountability claim by the CSV's author, reviewed like any other
roster change.

## CLI (the two lifecycle transitions)

```
lifecycle provision --manifest agent.yaml --owner "Don Hagell" --domain finance \
  --grantor "Don Hagell" --ttl-days 30 [--name "Display Name"] \
  [--manifest-ref /data/manifests/agent.yaml] [--out report.json]

lifecycle decommission <agent-id> --by "Don Hagell" --reason "project ended" \
  [--out report.json]
```

Both are CLI-only on purpose: they create and destroy authority, so they
want a human at a keyboard, not an HTTP route. Exit 0 = done, 1 = refused or
partially failed.

`provision` runs **validate -> register -> cap -> rate limits -> mint**. An
INVALID manifest, or `enforcement.rate_limits` the governor would refuse
(unknown period, duplicate entry, rate limits without a `spend_cap`), exits 1
with **zero side effects**. After that the steps run in
order and stop at the first failure — the `ProvisionReport` lists every step
with its status and nothing is rolled back, because reporting a
half-provisioned agent as provisioned is the worse failure. The cap comes
from `SpendCapConfig.from_manifest` — the **governor's own** arithmetic
(`round`, never `int()`), so the cap written here and the cap the governor
would derive cannot differ by a cent. A mint refusal from
delegation-authority (the DOA roster gate's 403/422, a 503 from an
unreadable roster) is reported **verbatim**, status and body.
The rate-limit step uses the governor's own loader
(`spend_governor.provisioning`, the one `governor set-cap --from-manifest`
uses), after the cap because `PUT /rate-limits` 404s for an uncapped agent. A
declared set is PUT, replacing whatever the governor held, and reported as a
`rate_limits` step (`N enforced, M declared-unenforced`; a `session` entry is
named DECLARED, NOT ENFORCED). With nothing declared a stale set is cleared,
and when the governor holds none, or is a pre-D1 governor with no route,
nothing is sent and no step is reported. A refused PUT or an unreachable
governor is a failed `rate_limits` step, and no token is minted.

`decommission` runs **revoke every token -> kill (only if `active`) ->
registry `retired` -> ledger**. Unknown agent: exit 1, nothing created, no
ledger event. Already `retired`: a recorded no-op
(`lifecycle.decommissioned{noop: true}`), exit 0, **no second kill**. A 502
from the ledger-first revoke is reported and the run *continues* act-first,
exiting non-zero at the end — an audit outage must never leave an agent
holding authority.

`tools/provision_ssl_agents.py` is a thin wrapper over `provision`: it keeps
the single-port proxy contract, the six-service health gate, the AGENTS
table, the token cache and the post-provision probes, and no longer does its
own `PUT /caps` or `POST /tokens`.

## API

```
lifecycle serve [--host 127.0.0.1] [--port 8012] [--roster owners.csv] [--every 86400]
```

| Route | Method | What |
|---|---|---|
| `/health` | GET | open; reports `roster_configured` and `every` |
| `/sweep` | POST | run a sweep now; body `{roster_csv?, expiry_days?, reattest_days?, operator?, auto_kill_orphans?}` (unknown keys ⇒ 422) |
| `/findings` | GET | the last sweep report (with its `swept_at`), plus `last_tick` once the scheduler has ticked; 404 before any sweep, carrying the last tick so a skip is explainable |

Roster resolution: the request's `roster_csv`, else the file at
`FIELD_LIFECYCLE_ROSTER`. With neither, `POST /sweep` answers **503** — an
empty roster would orphan every agent, so refusing is the safe answer.

`--every N` (env `FIELD_LIFECYCLE_EVERY`, 0 = off) runs a sweep in a
background thread, first tick **after** the interval so container start never
depends on a roster being present. A tick with no roster records a skip
(`lifecycle.tick_skipped` on the ledger plus `last_tick.json`) rather than
sweeping an empty roster; a tick that raises is logged and the loop continues.
Skips get their own file on purpose: both estates ship with the scheduler armed
and no roster, so a daily skip would otherwise overwrite the `swept_at` that is
the only evidence a real sweep ever ran.
**The scheduler never arms auto-kill** — that needs an explicit `true` in a
request body, and no environment variable can set it.

Env: `FIELD_LIFECYCLE_ROSTER`, `FIELD_LIFECYCLE_EVERY`, `FIELD_LIFECYCLE_URL`
(callers), plus the usual `FIELD_REGISTRY_URL` / `FIELD_DELEGATION_URL` /
`FIELD_LEDGER_URL` / `FIELD_KILLSWITCH_URL` and `FIELD_SHARED_SECRET`.
`provision` also reads **`FIELD_GOVERNOR_URL`** for its cap step; unset, it
targets `http://127.0.0.1:8006` and the run stops at `cap` behind a proxy.

## Findings → ledger events

| Finding | Ledger event | Default action |
|---|---|---|
| Token lapsing within horizon | `lifecycle.expiring_authority` | report (renew or let die — deliberately) |
| Last attestation older than the re-attestation period | `lifecycle.reattestation_due` (payload gains `basis` + `attested_by`, existing keys unchanged) | report |
| Owner not on roster | `lifecycle.orphan` | **escalate only** — auto-kill requires the flag |
| Witness stale or absent (X4; only where `FIELD_WITNESS_EVERY` is set and not blank — on the GB10 only once A5 sets it) | none — `SweepReport.witness` (`stale` / `none` / `unavailable` / `misconfigured`), exit 3 | report |
| Agent decommissioned | `lifecycle.decommissioned` (`{by, reason, tokens_revoked, killed}`; a repeat carries `noop: true`) | the transition itself |

**Re-attestation basis.** `attested_at`, falling back to `created_at` when
nobody has ever attested — and never the registry record's edit timestamp.
Any PATCH moves that one, so before v1.2 a kill/revive cycle reset the
staleness clock to zero and hid the agent completely. `registry attest <id>
--by NAME` (or `POST /agents/{id}/attest`) is the only thing that moves it.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| A witnessing estate's latest `anchor.remote{estate: FIELD_WITNESS_ESTATE_WATCHED (fly)}` older than 3 × `FIELD_WITNESS_EVERY`, or none, is a finding; an estate without a witness never gets one | **Enforced in code** (reporting) | `tests/test_witness_finding.py`: fresh (exactly 3 × is not older) ⇒ none, stale ⇒ `stale`, none or only another estate's ⇒ `none`, unset or blank (the GB10 compose default before A5) ⇒ none and no read, a set-but-unusable interval ⇒ `misconfigured`, ledger down / not a list / unreadable `ts` / a client without `events` ⇒ `unavailable` with the rest of the sweep run; real `LedgerClient` against the real ledger app; CLI exit 3 for every finding and 0 when fresh or unset; persisted in `/findings`; `lifecycle serve` builds the watch from the environment. Freshness is by ledger `ts`; signatures are NOT checked here (`ledger verify-witness --pubkey` does) |
| Expiring/stale/orphaned authority is detected deterministically | **Enforced in code** | date arithmetic + roster set membership; tests |
| Auto-kill NEVER happens without the explicit flag | **Enforced in code** | adversarial test: flag off ⇒ orphan stays active |
| Auto-kills go through kill-switch and land on the ledger | **Enforced in code** | reason string names the sweep; test |
| Sweeps are idempotent (no duplicate kills on re-run) | **Enforced in code** | second sweep sees status ≠ active; test |
| Auto-kill cannot be armed over HTTP except by a literal JSON `true` | **Enforced in code** | `StrictBool` — `"true"`, `"1"`, `1`, `"yes"`, `"on"` are all 422 (parametrized adversarial test); no flag ⇒ orphan stays `active` with the kill spy at zero; the arming path is itself tested so the negatives mean something; the grep-guard enumerates every env key the module reads and none contains `AUTO_KILL` |
| A sweep with no roster refuses (503) instead of sweeping an empty one | **Enforced in code** | test: 503, nothing ledgered — an empty roster would orphan every agent |
| An `aliases` string clears an orphan exactly like the owner string, and nothing looser does | **Enforced in code** | `tests/test_roster_aliases.py`: alias match (engine, served roster file, CLI exit 0); a substring of an alias, a whitespace variant and an unlisted owner stay orphans (CLI exit 3); blank alias entries and aliases on an owner-less row match nothing; `roster_size` counts owners; a roster without the column parses as before; each guard mutation-checked |
| An unquoted comma in `owners.csv` is refused when it leaves MORE fields than the header, or a value starting with whitespace — space, TAB, NBSP, U+3000 — after the comma (`Name, Org`) | **Enforced in code** | both raise a `ValueError` naming the line, before any sweep work: `test_an_unquoted_comma_is_refused_by_name` (three fields), `test_an_unquoted_comma_with_exactly_the_header_field_count_is_refused` (two fields under `owner,aliases` and under the legacy `owner,department`); `POST /sweep` answers 500 and a scheduled tick reports `ok: false` (tests); the CLI exits 1 (not 0, not 3), writes no ledger event and attempts no kill even with `--auto-kill-orphans` (`test_cli_sweep_refuses_an_unquoted_comma_and_kills_nothing`). An unquoted comma with no following whitespace and no more fields than the header is NOT detected — see LIMITS |
| The scheduler thread starts with the app, is a daemon, and stops on shutdown | **Enforced in code** when `--every` or `FIELD_LIFECYCLE_EVERY` is set | `test_scheduler_thread_actually_starts_and_stops_with_the_app`, `test_every_is_read_from_the_environment_when_not_passed`, `test_no_scheduler_thread_when_every_is_zero` |
| A tick waits the full interval before firing, and one raising tick does not stop the loop | **Enforced in code** | `run_every` injected-sleep tests |
| A roster-less tick never overwrites the `swept_at` that proves a sweep ran | **Enforced in code** | skips go to `last_tick.json`; `test_a_skipped_tick_never_erases_the_swept_at_that_proves_a_run` |
| Re-attestation staleness cannot be hidden by editing the record | **Enforced in code** | the basis is `attested_at` else `created_at`; a grep-guard test fails if the module reads the record's edit timestamp again, and an adversarial test runs a kill/revive/patch cycle and still finds the agent stale |
| `provision` of an INVALID manifest has zero side effects | **Enforced in code** | validate runs before any client call; the test asserts empty registry, no cap, no token and an empty ledger |
| The provisioned cap equals the manifest's cents | **Enforced in code** | `SpendCapConfig.from_manifest` (the governor's own `round`); tests pin 50000 cents daily for `limit: 500` and **29 cents for `limit: 0.29`, where `0.29 * 100` is 28.999999999999996 so `int()` truncates to 28** — the test asserts that disagreement first, so it cannot quietly stop proving anything |
| `provision` loads the manifest's `enforcement.rate_limits` after the cap, and a failed rate-limit step mints nothing | **Enforced in code** | `tests/test_provision_rate_limits.py`: declared set loaded (window throttles after max; `session` reported as declared-unenforced), re-provision without `rate_limits` clears the stale set, a governor that refuses the set (pre-D1 404) or is unreachable fails the `rate_limits` step with no token minted and the earlier steps reported, nothing declared against a pre-D1 governor still provisions in four steps |
| An unknown rate-limit period or a duplicate entry is refused before any side effect | **Enforced in code** | `rate_limits_from_manifest` at step one raises `LifecycleError`; the test asserts no registry row, no cap, no token and an empty ledger |
| A mint refusal is passed through, never reinterpreted | **Enforced in code** | the step carries the upstream status and body; test drives a real 403 `D.grantor` from the DOA roster gate |
| A partial provision is reported as partial | **Enforced in code** | `ProvisionReport.steps` + `ok: false`; nothing is rolled back and the CLI exits 1 naming the step that stopped it |
| `provision` refuses a retired agent | **Enforced in code** | 409 at the register step, before the PATCH and before the cap. Without it, re-provisioning a decommissioned agent rewrote `owner` (its audit attribution) and `manifest_ref` (what the kill-switch resolves its halt endpoint from) and installed a live spend cap on it — the mint refused, so the run looked like a clean failure while three side effects had already landed. Adversarial test asserts all three are unchanged, plus a positive test that an ACTIVE agent is still updated |
| `decommission` of an unknown agent changes nothing | **Enforced in code** | adversarial test: registry unchanged, zero ledger events, kill spy at zero |
| A second decommission is a no-op, not a second kill | **Enforced in code** | adversarial test: `noop: true` on the ledger, one `kill.agent` in total, kill spy called once |
| An already-killed agent gets no second `kill.agent` | **Enforced in code** | the kill step is skipped unless the status is `active`; test |
| A decommission survives a revoke failure and still halts the agent | **Enforced in code** | act-first: a 502 revoke is recorded in `revoke_failures`, the kill and the retire still happen, and the run exits non-zero |
| A retire cannot be undone **from the kill-switch or the console** | **Enforced in code** (kill-switch) | all four status-writing kill-switch routes answer 409 or skip for a retired agent (`/kill`, `/revive`, `/kill/domain`, `/drill`); the console hides the button. Test in this suite drives it end to end from a real decommission. `PATCH /agents/{id}` on the registry is **not** covered — see LIMITS |
| The ledger's retention check is part of every CLI and served sweep: a non-ok answer, or no answer, is a `retention_policy` finding and exit 3; ok is `None` | **Enforced in code** | `tests/test_retention_finding.py`: `test_lifecycle_retention_finding_present_and_exit_3` (violation ⇒ exit 3; ok ⇒ `None` and exit 0; a ledger client without the check ⇒ not checked; an all-empty `no_estate_policy` finding still exits 3 — `is not None`, never truthiness; ledger down ⇒ `unavailable`, exit 3, the sweep completed), `test_every_non_ok_answer_is_a_finding_and_writes_no_ledger_event`, `test_a_ledger_that_cannot_answer_is_unavailable_and_the_sweep_carries_on`, `test_real_ledger_client_end_to_end_and_ledger_down` (the real `LedgerClient` against the real ledger route), `test_served_sweep_persists_the_finding_and_old_reports_still_load` (in `GET /findings`; a pre-C2 `last_sweep.json` still validates), `test_lifecycle_serve_wires_a_ledger_client`. The finding is estate-level: retention is one policy for the one chain, and each manifest's `retention_days` is a floor the estate must meet |
| `attested_by` is the human who attested | **Declared only** | a recorded string, not an authenticated identity (registry README says the same) |
| The roster is current and complete | **Declared only** | the sweep is as good as the CSV HR exports |
| An alias names the same human as its owner | **Declared only** | whoever writes the CSV declares it; nothing resolves identity |
| Re-attestation actually happens after the flag | **Declared only** | the sweep reports staleness; a human must call `registry attest` — the platform records the claim, it does not verify the review happened |
| The sweep is actually running on the estate | **Declared only** | until a `swept_at` from that estate's `GET /findings` is on record — the service is deployed on both estates (X0, 2026-09-12), but `FIELD_LIFECYCLE_ROSTER` stays unset on both until arming step A1, so every scheduled tick is a recorded skip |

## LIMITS

- Re-attestation runs from `attested_at`, else `created_at`. That is a
  record of someone *claiming* they reviewed the agent, with a name attached
  — it is not evidence that a review happened, and the name is not
  authenticated.
- **A decommission is final to this CLI, not to the registry.** `provision`
  refuses a retired agent and `decommission` is a no-op on one, but
  `PATCH /agents/{id}` will still set `retired` back to `active` — see the
  bullet below. To bring a decommissioned workload back, prefer a new agent
  id: the old record's ledger history then stays readable as a decommission
  rather than becoming a resurrection.
- **Neither transition is atomic and neither is rolled back.** A provision
  that fails at `mint` leaves a registered, capped agent with no token; a
  decommission that fails at `retire` leaves a halted agent that is still
  `killed`, not `retired`. Both reports say exactly where the run stopped —
  read them before re-running.
- `decommission` revokes tokens one at a time and kills serially; a large
  estate should expect it to take as long as those calls do.
- `provision` trusts the manifest for the agent id, the scope and the cap.
  `--owner`, `--domain` and `--grantor` are the operator's assertions and
  are recorded, not verified.
- **A retirement is final at the kill-switch, not at the registry.**
  `PATCH /agents/{id}` with `{"status": "active"}` puts a retired agent back
  to `active`, returns 200 and ledgers a plain `registry.status_changed`.
  The kill-switch's four 409s (`/kill`, `/revive`, `/kill/domain`, `/drill`)
  close the *operator console* path, which is the one a CISO clicks at 2 a.m.
  The registry route stays open on purpose — it is the correction path for a
  decommission made in error — so treat `retired` as reversible by whoever
  can reach the registry API directly, and read the ledger to see it happen.
- Owner matching is exact-string (case-insensitive), not identity-resolved:
  "J. Smith" vs "Jane Smith" are different people to this sweep — unless the
  CSV lists one as an alias of the other.
- **Aliases are declared by whoever writes the CSV.** An alias is the CSV
  author's claim that two strings are one accountable human; the sweep
  cannot verify it, and a wrong alias hides a real orphan. Review alias lines
  like any other change to who is accountable for an agent.
- An unquoted comma with no whitespace after it, in a row with no more
  fields than the header (`Don Hagell,Spin State Labs` under `owner,aliases`,
  or under a wider header with trailing columns left off), is
  indistinguishable from an owner plus an alias and is read as one. Only the
  more-fields and comma-whitespace shapes are refused.
- Auto-kill only touches `active` orphans; killed/retired agents are
  reported but untouched.
- The scheduler is in-process and its state is not persisted: a restart
  restarts the interval, and `swept_at` in `GET /findings` is the only
  evidence a sweep actually ran. It proves a run, never a cadence.
- `POST /sweep` is synchronous: a sweep of a large estate holds the request
  open (the CLI remains the path for long or scripted sweeps).
- The retention finding is only as fresh as the ledger's answer at sweep
  time, and is reported, not escalated: it writes no ledger event, so the
  ledger history does not show it (the persisted `GET /findings` does).
  `create_app()` checks retention only when a client is passed in
  (`lifecycle serve` passes a `LedgerClient`); a ledger client that has no
  `retention_check` (a pre-C2 client, a test stand-in) is not checked.
- The served sweep reaches the registry, delegation and ledger with the
  caller's estate credentials; on a secret estate every route except
  `/health` needs `x-field-auth`, so a browser cannot drive it.
