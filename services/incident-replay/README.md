# incident-replay

Deterministic incident reconstruction. Given a time window and an agent id,
answer the three questions every incident review starts with — **who granted
authority, what ran, which clause failed** — as a RACI post-mortem whose
R/A/C/I are read from registry, grant and manifest, with labeled defaults.
FIELD letter **L** (Ledger). Exec owner: **CISO**.

## API & CLI

`POST /replay` `{agent_id, since, until}` → structured post-mortem ·
`POST /replay/markdown` → the same as markdown · `GET /health`

```
replay run <agent-id> --since 2026-08-08T00:00:00Z --until 2026-08-09T00:00:00Z [--markdown pm.md]
replay serve [--port 8007]
```

`since`/`until` must be ISO 8601 instants with a time (422 otherwise); a
naive instant is read as UTC. A date alone is refused with 422: the ledger
would read `until=2026-08-18` as 00:00:00 UTC and silently drop that day
(attest reads a date-only `--until` as the END of the day — the conventions
differ, so replay makes the caller say which instant). The agent's
`manifest_ref` is resolved by the shared field-core resolver (B0): absolute, or
relative to `FIELD_MANIFEST_DIR` (default: the process working directory).

## What the report contains

- **Ledger integrity banner** — the chain is verified before anything is
  reported; a broken chain brands the whole report INTEGRITY FAILED. A ledger
  too busy to take a consistent snapshot (`/verify` ok=false, reason
  `ledger busy: …`) brands it INTEGRITY NOT VERIFIED — retry: not a break,
  and never OK. `ledger_integrity_status` is `intact` | `broken` |
  `unverified`.
- **Integrity note** — when the window starts before the earliest LIVE ledger
  event (C2 segments archived out of the live ledger), the report says so and
  how many segments are archived: those events cannot appear in it.
- **Agent** — registry record (owner, domain, status, manifest ref).
- **Who granted authority** — every delegation grant overlapping the window:
  issued at or before `until` and not yet expired at `since` (a grant is
  expired once `now >= expires_at`, as `DelegationToken.status` rules), with
  grantor, scope, expiry and revocation time.
- **What ran** — chronological ledger timeline with event hashes; each entry
  carries its `action` and `enforced` (true: an applied sentinel verdict;
  false: a log-only shadow verdict).
- **Which clause failed first** — the first `conformance.block` /
  `escalate` **or** log-only `conformance.shadow_block` / `shadow_escalate`
  (clause from `would_block`), whichever the ledger recorded first; shadows
  are labeled `(log-only, not enforced)`.
- **RACI** — every party is labeled with its source (also returned as the
  `raci_sources` map), and `manifest_resolved` / `manifest_detail`
  (`ok` | `no_ref` | `missing` | `invalid`) say whether the manifest was read:

  | Role | From data | Fallback |
  |---|---|---|
  | Responsible | registry `owner` `(agent owner)` | `<unregistered agent>` |
  | Accountable | a grant's grantor, with the grant's status judged **at the first failure's ledger timestamp** (the `DelegationToken.status` rule) and scope by exact string membership (the sentinel's rule): for a `D.expired` / `D.revoked` failure, the most recently issued grant covering the action whose status then was expired / revoked — searched across every grant for the agent, not only the window `(expired grant covering '<action>')` / `(revoked grant covering '<action>')`; otherwise the earliest window-overlapping grant covering the action that was in force then `(grant covering '<action>')` | earliest overlapping grant `(earliest overlapping grant)`; none ⇒ `<no grantor found>` |
  | Consulted | manifest `enforcement.kill_switch.authorized_operators` when non-empty after dropping blank entries `(manifest kill_switch.authorized_operators)` | the exec that owns the failed clause's FIELD letter `(default)` |
  | Informed | manifest `identity.principal` (` — org`), when not blank `(manifest identity)` | `CEO / board (attestation-reporter) (default)` |

  The grant Accountable was read from is returned as `accountable_grant` and
  printed under the RACI table — for `D.expired` / `D.revoked` it may have
  lapsed before the window and so be absent from "Who granted authority".

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every number/line is a query result from ledger+registry+delegation+manifest | **Enforced in code** | pure query engine; `method` field says so on every report |
| Tampered ledgers cannot produce a clean report | **Enforced in code** | `/verify` runs first; adversarial test edits the trail and asserts the FAILED banner |
| A busy ledger (`/verify` ok=false, reason starting `ledger busy:`) is reported INTEGRITY NOT VERIFIED — never CHAIN BROKEN, never OK; any other ok=false stays CHAIN BROKEN | **Enforced in code** | `tests/test_raci_from_data.py::test_busy_ledger_is_unverified_never_a_broken_chain_and_never_ok` (the real store's snapshot raises `LedgerBusy`), `::test_any_other_verify_failure_is_still_a_broken_chain` |
| Window filtering is exact (ISO interval, inclusive) | **Enforced in code** | test |
| A date-only `since`/`until` is refused (422), never sent to the ledger as a silent 00:00:00 UTC bound | **Enforced in code** | `::test_date_only_window_bound_is_refused_422` (4 shapes, both routes) |
| No LLM in the report path | **Enforced in code** | there is simply no LLM dependency; optional narration would be a separate, labeled layer (not in v0.1) |
| RACI Responsible = registry owner, labeled | **Enforced in code** | `tests/test_raci_from_data.py::test_responsible_is_registry_owner_labeled`, `::test_unregistered_agent_defaults_every_manifest_role` |
| RACI Accountable = the grantor of the earliest covering grant (exact membership) that was **in force at the first failure's ledger timestamp**, else the earliest overlapping grant, else `<no grantor found>` — each labeled. A grant revoked before the failure, or issued after it, is never "covering" | **Enforced in code** | `::test_covering_grant_beats_earlier_non_covering_grant`, `::test_earliest_covering_grant_wins_when_several_cover`, `::test_d_scope_failure_falls_back_to_earliest_overlapping_grant`, `::test_no_failure_uses_earliest_overlapping_grant`, `::test_no_grants_means_no_grantor_found`, `::test_covers_is_the_delegation_token_rule`, `::test_accountable_is_never_a_grant_revoked_before_the_failure` and `::test_accountable_is_never_a_grant_minted_after_the_failure` (real delegation-authority), `::test_covering_grant_must_be_in_force_at_the_failure_instant` (7 boundaries), `::test_status_at_is_the_delegation_token_rule`, `::test_earliest_grant_is_chosen_by_instant_not_string` |
| RACI Accountable for a `D.expired` / `D.revoked` failure = the most recently issued grant covering the action that had expired / been revoked by the failure, from every grant for the agent (the presented token may have lapsed before `since`); no such grant ⇒ the rule above | **Enforced in code** | `::test_d_expired_accountable_is_the_lapsed_grant_even_before_the_window` and `::test_d_revoked_accountable_is_the_revoked_grant` (real delegation-authority), `::test_lapsed_clause_names_the_most_recent_grant_that_lapsed_that_way` (4 cases), `::test_lapsed_clause_without_a_lapsed_covering_grant_uses_the_general_rule` |
| RACI Consulted = manifest kill-switch operators when non-empty (blank entries dropped), else the labeled clause-letter default | **Enforced in code** | `::test_consulted_from_manifest_operators_when_non_empty`, `::test_empty_or_absent_operators_use_clause_default`, `::test_blank_manifest_names_are_not_parties` |
| RACI Informed = manifest principal (— org) when not blank, else the labeled default | **Enforced in code** | `::test_informed_principal_and_org`, `::test_informed_principal_only`, `::test_blank_manifest_names_are_not_parties` |
| No / missing / unparseable / schema-invalid manifest never crashes the replay; defaults labeled, `manifest_resolved=false` with the resolver's reason | **Enforced in code** | `::test_unresolvable_manifest_defaults_labeled_no_crash` (4 cases) |
| Log-only shadow verdicts are failures, clause from `would_block`, labeled `(log-only, not enforced)`; first failure is whichever was ledgered first | **Enforced in code** | `::test_shadow_block_is_first_failure_labeled_log_only`, `::test_shadow_escalate_clause_from_would_block`, `::test_first_failure_shadow_before_enforced`, `::test_first_failure_enforced_before_shadow` |
| Grant/window overlap, grant status at the failure, grant ordering and the earliest-live comparison use instants, not strings; overlap is issued ≤ `until` (inclusive) and expires > `since` (a grant expiring exactly at `since` had expired); a naive bound is UTC | **Enforced in code** | `::test_grant_window_overlap_compares_instants_not_strings`, `::test_grant_expiry_side_compares_instants_not_strings`, `::test_window_overlap_boundaries_match_the_token_status_rule`, `::test_earliest_grant_is_chosen_by_instant_not_string`, `::test_lapsed_clause_names_the_most_recent_grant_that_lapsed_that_way`, `::test_naive_window_bounds_are_read_as_utc`, `::test_earliest_live_note_absent_when_window_starts_at_or_after_it[mixed-offset-after]` |
| Window starting before the earliest live event carries an integrity note; a ledger without the fields gives no note; an unreadable `/health` never fails the replay | **Enforced in code** (replay side) — the ledger fields (`earliest_live_ts`, `earliest_live_index`, `archived_segments`) are the C2 `/health` contract, tested here against a **stub** ledger only | `::test_earliest_live_note_present_when_window_starts_before_it`, `::test_earliest_live_note_absent_on_pre_c2_ledger`, `::test_earliest_live_note_absent_when_nothing_archived`, `::test_unreadable_ledger_health_never_crashes_the_replay` |
| The trail is *complete* (nothing acted without logging) | **Declared only** (here) | completeness is the sentinel's fail-closed job; replay reports what the ledger holds |

## LIMITS

- Replay is only as complete as the ledger: actions taken outside the
  sentinel/decorator perimeter never became events and cannot be replayed.
- RACI is read from records, not an org lookup. Grantor and operator names
  are recorded strings, not authenticated identities. The Consulted fallback
  is a static clause-letter → exec map; org charts differ.
- Accountable names a grant that COVERS the failing action, which need not
  be the token presented at the failing check: conformance events do not
  record the token id. A `D.scope` block on an action no grant IN FORCE at
  the failure holds has no covering grant (labeled `earliest overlapping
  grant`), even when a covering grant is minted later in the window; a
  `D.scope` block raised by the MANIFEST scope (action in an in-force token,
  not in the manifest) does, and is labeled `grant covering '<action>'`.
- Grant status is judged at the failure event's LEDGER timestamp, which the
  ledger stamps a few milliseconds after the sentinel's check: a grant that
  expired or was revoked inside that gap is not counted as in force.
- For `D.expired` / `D.revoked` the grant named is the most recently issued
  covering grant that had lapsed that way — a choice, since the presented
  token is not recorded. The sentinel checks expiry before scope, so the
  presented token need not cover the action; a lapsed grant is named only
  when it does, otherwise the in-force / overlapping rule applies. This
  search spans every grant for the agent, so it does not depend on `since`.
- A grant marked revoked with no `revoked_at` (not written by
  delegation-authority, which always stamps it) has an unknown status at the
  failure: it is never named as covering, in force or revoked.
- "Who granted authority" and the `earliest overlapping grant` fallback use
  issuance and expiry only: a grant revoked before the window still appears
  there (Revoked: yes, with its time).
- The manifest is read at replay time, not as it was during the window: an
  edited manifest changes Consulted/Informed for past incidents.
- The earliest-live note needs a C2 ledger (`/health` `earliest_live_ts` +
  `earliest_live_index` > 0). A pre-C2 ledger never produces it; an
  unreadable `/health` or unparseable `earliest_live_ts` produces an
  `earliest-live check unavailable` note instead.
- Timestamps are compared as datetimes; a naive timestamp is read as UTC
  (the ledger's rule). A date-only bound is refused rather than expanded.
- A busy ledger yields a report whose events are unverified: retry until
  `ledger_integrity_status` is `intact`. A `/verify` that answers an HTTP
  error fails the replay (500) rather than rendering a report.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
