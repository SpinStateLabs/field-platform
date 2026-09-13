# attestation-reporter

One command renders the quarterly governance board pack from **live
services**: agents in production, conformance rate, blocks and escalations,
kill activity, expiring authorities, federation crossings, ledger
integrity — counted over a stated **window**, and signable with a named
signer's Ed25519 key (a pack rendered without one is marked **UNSIGNED
DRAFT**, and the served pack is always one). All FIELD letters. Exec owner:
**CEO / board**.

## The rule: no number without a source

Every metric in the pack — JSON and HTML — carries the **literal HTTP query
it came from**, printed next to the value. The rule is enforced at the
model level: a metric cannot be constructed with a value and no source, and
an unreachable service produces an **`unavailable`** metric (query still
shown), never a fabricated zero. The printed query is the request that was
sent, byte for byte (a `+` in a UTC offset is printed `%2B`, as sent).

## The window

Every metric says what it is counted over (`basis`):

- **`window`** — every figure derived from ledger events (each whose query
  hits `/events`) is counted inside `window`, and its printed query carries
  `since=`/`until=`. Re-running that query reproduces the count while those
  events are in the live ledger (less any gate-verification records the
  metric's note says it excluded).
- **`point_in_time`** — registry counts, the token list (issued, revoked,
  expiring ≤ 30 d), open spend escalations, chain integrity and the retention
  figures are as they stood at generation; each says so in its note.

`window` is resolved before any service is queried:

| Given | `window.kind` | Bounds |
|---|---|---|
| `--period 2026-Q3` or `--period "Q3 2026"` | `quarter` | the UTC calendar quarter, `2026-07-01T00:00:00+00:00` .. `2026-09-30T23:59:59.999999+00:00` |
| `--since` and/or `--until` | `range` | inclusive, normalised to UTC instants before any query: `Z` is `+00:00` and a naive timestamp is UTC, as the ledger compares them; a date alone is the start (`since`) or the END (`until`, its last microsecond) of that UTC day — NOT as the ledger reads a raw date, which is always the START of the day (so `?until=2026-09-30` sent straight to the ledger stops at midnight, while this window includes that day). Every query the pack sends and prints carries the normalised instants. No `--until` ⇒ the generation instant (so the printed queries reproduce); no `--since` ⇒ an open start |
| neither | `all-time` | no bounds on any query: every event in the LIVE ledger |

`--period` is strict (`YYYY-Qn` or `Qn YYYY` in ASCII digits, nothing else)
and mutually exclusive with `--since`/`--until`; a free-form caption, a blank
(`?since=` included — never all-time), `since` after `until`, a year 0000, or
a bound whose UTC instant falls outside years 0001..9999 is refused (CLI exit
2, API 422). `since` equal to `until` is a one-instant window, not an error.

## CLI

```
attest render [--out board-pack/] [--period 2026-Q3 | --since T --until T] [--org NAME]
              [--signer NAME --sign-key PEM] [--pdf/--no-pdf]
attest verify board-pack.json --pubkey PEM
```

`render` writes `board-pack.json`, `board-pack.html`, and (best-effort)
`board-pack.pdf` via headless Edge/Chrome if one is installed — otherwise
it says so and ships HTML.

- **Signing.** `--signer "Don Hagell" --sign-key signer.pem` (an Ed25519 PEM
  private key) signs `board-pack.json`. The pack then carries `signed: true`,
  `signer`, `signed_at`, `key_fingerprint` (sha-256 over the raw public key)
  and `signature`, and the HTML footer names the signer and the fingerprint.
  Without them the pack is an **UNSIGNED DRAFT**: `signed: false`, and the
  HTML opens with an `UNSIGNED DRAFT` banner right after `<body>`. A blank
  signer, a signer without a key, a key without a signer, or a key that does
  not load (missing, a directory, not PEM, a public key, not Ed25519,
  encrypted, an algorithm `cryptography` does not know) is refused with exit
  2 before any service is queried or any file is written.
- **What is signed.** The bytes are
  `canonical_manifest_bytes(pack.model_dump(mode="json", exclude={"signature"}))`
  — the whole pack with the `signature` key absent: org, period, window,
  `generated_at`, method, every section title and every metric field, and
  the signer fields. Only `board-pack.json` is the signed artefact; the HTML
  and PDF are renderings of it.
- **Verifying.** `attest verify` canonicalises the RAW parsed JSON (minus its
  `signature` key), never a re-validated model, so an added key fails as
  surely as an edited one. The file is parsed strictly: a key repeated in
  one object is refused (`json.loads` keeps the last occurrence, a human or a
  first-wins parser reads the first), and so is `NaN`/`Infinity`. The
  `signature` string must be the one canonical base64 spelling of its 64
  bytes, and a valid signature over an object that is not a board pack is
  refused. Exit 0: valid, naming the signer. Exit 1: an unsigned pack
  ("nothing to verify"), the wrong key (both fingerprints named), any edit
  after signing, not canonical JSON, a public key that does not load, not a
  board pack, or an unreadable file.

## API

```
attest serve [--host 127.0.0.1] [--port 8013]
```

| Route | Method | What |
|---|---|---|
| `/health` | GET | open |
| `/pack` | GET | the board pack as JSON; `?period=` or `?since=`/`?until=` set the window (rules above); `?org=` |
| `/pack.html` | GET | the same pack rendered |

The served pack is a **windowed, UNSIGNED draft**. A bad window answers
**422** with no pack body — never all-time counts under a window the caller
asked for. The served pack is **always** unsigned: an unattended server
cannot be the named human signer, so the API module has no signer and no key
(F4 decides whether an estate key may sign served packs). PDF stays CLI-only.

Every route except `/health` sits behind `x-field-auth` when
`FIELD_SHARED_SECRET` is set — including `/pack.html`, so a browser cannot
open it on a secret estate. That is deliberate: the page carries estate
figures. Callers use `FIELD_ATTEST_URL`.

## What the board sees

| Section | Metrics (each with its query and basis) |
|---|---|
| Ledger integrity | chain INTACT/BROKEN — the number the rest stand on, listed first (point-in-time: the whole live chain; a window that starts before the earliest LIVE event says so) · estate ledger retention policy (days) · manifests declaring more retention than the estate keeps (ids and unresolvable refs in the note) |
| Agents | registered · in production · currently killed (point-in-time) |
| Conformance | rate = ALLOW / all verdicts **incl. shadow**, plus five raw counts (allow/block/escalate + shadow_block/shadow_escalate — log-only would-blocks, labeled "not enforced") (window) |
| Enforcement | kill activations · drills completed (window) · open spend escalations (point-in-time) |
| Delegation | tokens issued · revoked (point-in-time) |
| Expirations & re-attestation | authorities expiring ≤ 30 d (point-in-time) · re-attestation-due sweep events · distinct agents flagged · expiring-authority sweep events · distinct tokens flagged (window) |
| Federation & lifecycle | crossings allowed/blocked · orphan escalations (window) |
| Gate verification | ONE row: events by the rule-7 canary agents in the window, per agent in the note — excluded from every figure above |

The canary agents are exactly `canary-gb10`, `canary-fly`,
`canary-gb10-retired` and `canary-fly-retired` (the ids in
`tools/estate_probe.py`) — exact ids, never a prefix. Their events,
registry records, tokens, escalations and retention findings are dropped
from every governance metric, and a metric that dropped any says how many.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every number carries its literal source query | **Enforced in code** | `Metric` model validator + test iterating every metric |
| Unreachable services show as unavailable, never zero | **Enforced in code** | adversarial test with the governor down |
| A tampered ledger surfaces as BROKEN in the pack, with the ledger's break reason — for an edited field, a record made unparseable (non-JSON, a required key deleted) and two middle records swapped | **Enforced in code** | integrity metric leads the pack; `test_broken_ledger_shows_in_pack` edits a field; `tests/test_c4_window_and_signature.py::test_on_disk_tampers_surface_as_broken_end_to_end_and_a_tail_deletion_is_the_limit` (real on-disk tampers through the real ledger app, single-file and rotated, the rotated ledger's closed segment also under a store opened after the edit: the ledger's `/verify` answers 200 `ok: false` with the tampered record's global `first_break_index`, and the pack reads `BROKEN — … unparseable record at index …` / `… link break at index …`). NOT detected: a deleted TAIL record — `/verify` answers `ok: true` over the shorter chain and the pack reads INTACT (pinned by the same test); only comparing the head with an anchor held off-box catches it (sealed-ledger). A deleted middle record is not tested here. A ledger process restarted on an open segment holding an unparseable record does not start (sealed-ledger LIMITS), so the pack then shows integrity **unavailable** (`ledger unreachable`), never INTACT |
| A ledger that refuses the pack (401/5xx) or is busy is shown as unavailable, never as BROKEN — and the note says which: no answer (`ledger unreachable`), refused (`HTTP 401/403`), `HTTP 503`, any other answer (`HTTP <code> … chain NOT verified`) | **Enforced in code** | `tests/test_c4_window_and_signature.py::test_integrity_is_unavailable_not_broken_when_the_ledger_refuses_or_is_busy` (a 401, a 503, the ledger's `ledger busy:` verification — and a real break whose reason merely contains "busy" stays BROKEN: only the prefix is busy), `test_a_ledger_that_answers_verify_without_a_result_is_not_verified_never_unreachable` (500, 404, 403, a 200 that is not a verification, connection refused, not configured) |
| Derived figures show their formula | **Enforced in code** | conformance note prints `allows / (a+b+e+sb+se)`; the distinct rows print theirs |
| The retention figures come from the ledger's `GET /retention/check`, and a ledger that cannot answer — or an estate with no policy — shows both as unavailable, never a number | **Enforced in code** | `tests/test_retention_metrics.py`: `test_attest_retention_metrics_present_and_ledger_down_unavailable` (both metrics in "Ledger integrity" with `GET …/retention/check`; ledger `None`, raising, or 401 ⇒ both unavailable with no value; served pack == rendered pack), `test_within_policy_counts_zero_and_no_policy_is_unavailable`, `test_registry_unreadable_by_the_ledger_keeps_the_policy_and_withholds_the_count`. Both are SCALARS (`Metric.value` is scalar-only): offending ids and unresolvable refs are in the note, and a count with unresolvable refs is labeled a lower bound |
| A log-only estate cannot read 100% conformant | **Enforced in code** | shadow verdicts count in the rate denominator + own labeled rows (S2-R); adversarial test stages shadow events |
| Every ledger-derived figure is counted inside the pack's window, and its printed query carries the window; an all-time pack carries none | **Enforced in code** | `tests/test_c4_window_and_signature.py`: `test_hand_chained_ledger_counts_only_in_window_events_and_stays_intact` (a hand-chained `events.jsonl` with timestamps on both sides of 2026-Q3, including offsets that read inside but fall outside ⇒ only in-window events counted, integrity INTACT), `test_every_ledger_derived_metric_carries_the_window_and_all_time_has_none` (iterates `all_metrics()`: each of the 16 `/events` metrics has `since=`/`until=` and `basis=window` and every printed query replays as the request; replaying each of the 12 single-query counts reproduces its value; every other metric is `point_in_time`) |
| `--period` is a strict UTC quarter; bounds are normalised as the ledger compares instants (`Z` = `+00:00`, offsets converted, a naive timestamp is UTC on any host zone); a date-only `since` is the START of that day and a date-only `until` the END of it — unlike the ledger's raw `?until=<date>`, which is its start (LIMITS); `--period` excludes `--since`/`--until` | **Enforced in code** | `test_parse_period_both_spellings_give_the_utc_quarter`, `test_parse_period_is_strict` (incl. year 0000 and non-ASCII digits), `test_normalise_bound_matches_the_ledgers_inclusive_bounds` (compared with sealed-ledger's own `parse_instant`), `test_a_naive_bound_is_utc_whatever_the_host_zone` (a child process under `TZ=JST-9`, so a UTC CI host still catches naive-as-local), `test_period_excludes_since_until_and_neither_is_all_time` |
| `GET /pack` served — a windowed, unsigned draft (`period` or `since`/`until`; a bad window ⇒ 422, never a 500 and never all-time; never signed) | **Enforced in code** | `test_served_pack_honours_since_until_and_period_and_is_always_unsigned` (served == rendered for the same window; a past window counts 0; 422 on both routes with no pack body; an injected engine that signs ⇒ 500; the API module never imports the signer), `test_a_one_instant_window_is_accepted_and_a_blank_bound_is_refused_everywhere` (`since == until` accepted; `?since=` / `?until=` ⇒ 422; `attest render --since ""` exit 2, nothing written), `test_out_of_range_windows_are_refused_never_a_server_error` (year 0000, non-ASCII digits, out-of-range UTC instants ⇒ 422 / exit 2); `tests/test_api.py` served pack equals `attest render` output |
| A signed pack's signature covers every field of `board-pack.json`; any edit, added key (a duplicated key included) or removed key fails `attest verify`; the wrong key is named | **Enforced in code** | `test_every_field_of_a_signed_pack_is_inside_the_signature` (every leaf of the dumped JSON mutated in turn — each metric's name/value/unit/source_query/status/note/basis, signer, signed_at, period, window.since, generated_at … — plus an added and a removed key), `test_verify_refuses_a_duplicated_key_a_non_finite_number_and_a_respelled_signature` (a forged `value` or `signer` placed AHEAD of the real one, a duplicated `signature`, `NaN`/`-Infinity`/`1e999`, the signature re-spelled with junk, flipped unused bits, no padding or an escaped newline, an unloadable public key, a valid signature over a non-pack object), `test_signature_is_over_the_dump_without_the_signature_key`, `test_wrong_key_is_named_and_a_blank_signer_is_refused`, `test_cli_render_signs_and_verify_exits_0_1_1` (exit 0 valid; 1 wrong key / edited / unsigned / JSON that is not an object) |
| A blank signer is refused; a key that does not load is an error, never a process exit and never an unsigned pack passed off as signed | **Enforced in code** | `test_wrong_key_is_named_and_a_blank_signer_is_refused`, `test_key_load_failure_raises_and_is_never_a_process_exit` (8 bad keys, incl. a PKCS#8 key under an unknown algorithm OID — `UnsupportedAlgorithm`, which is not a `ValueError` — ⇒ `InvalidSigningKey`; CLI exit 2 with nothing written and no service queried; the served app keeps answering) |
| An unsigned pack cannot be read as an attestation: `UNSIGNED DRAFT` banner right after `<body>` and `signed: false`; a signed pack's footer names the signer and key fingerprint | **Enforced in code** | `test_unsigned_banner_follows_body_and_the_signed_footer_names_signer_and_fingerprint`, `test_cli_render_signs_and_verify_exits_0_1_1` |
| Canary (gate-verification) activity is one labelled row and is excluded from every governance metric | **Enforced in code** | `test_canary_activity_is_one_labelled_row_and_excluded_from_every_governance_metric` (canary events of 12 types by all 4 ids, canary registry records, a canary token and a canary spend escalation: every governance metric unchanged, the row counts them, a lookalike id is still counted as governance), `test_canary_retention_findings_are_excluded_from_the_count`, `test_canary_ids_are_exactly_the_estate_probes` (pins the set to `tools/estate_probe.py`) |
| The lifecycle rows count sweep EVENTS in the window and say so; the distinct rows de-duplicate agents and tokens with the formula printed | **Enforced in code** | `test_lifecycle_sweep_rows_count_events_in_window_with_the_honesty_note` |
| A window that starts before the earliest live ledger event says so (C3's note) | **Enforced in code** | `test_earliest_live_note_when_the_window_starts_before_archived_history` (a real rotation + retention apply; both sides of the boundary: `since` exactly at the earliest live event ⇒ no note, one microsecond earlier ⇒ the note) |
| A ledger that cannot answer leaves every windowed figure unavailable, window still printed | **Enforced in code** | `test_ledger_down_every_ledger_metric_is_unavailable_never_a_number` |
| A valid signature means the named person approved the pack | **Declared only** | it proves the pack was signed with the private key whose fingerprint it names, and nothing was changed after; who holds that key, and that the `signer` string is that person, is key custody outside this service |
| The HTML and PDF are signed | **Declared only — not the case by design** | only `board-pack.json` is signed; the HTML footer is a rendering of the JSON's signer fields |
| The pack covers *everything the org runs* | **Declared only** | it covers what the platform governs; ungoverned shadow agents appear only via discovery/lifecycle findings |
| PDF fidelity | **Declared only** | best-effort headless print; HTML is canonical |

## LIMITS

- Windowed figures are reproducible; point-in-time figures are not. A pack
  for a past quarter counts that quarter's ledger events, but registry
  counts, the token list, open escalations, integrity and retention are as
  they stood when the pack was generated, not as they stood in the quarter —
  quarter-over-quarter trends in those still need packs archived per
  quarter (store them; they're evidence).
- Counts are counts of the LIVE ledger: once closed segments are archived
  (C2 retention apply), events in them are no longer returned by `/events`,
  so all-time counts, and any window reaching back into archived history,
  shrink with archival. The integrity note says when the window starts
  before the earliest live event (from the ledger's `/health`
  `earliest_live_index` / `earliest_live_ts`, and `/verify`
  `archived_segments`).
- A window counts events by their `ts`, stamped by the ledger's clock at
  append time, compared as instants with both bounds inclusive. A date alone
  in `--until` means the END of that day here, while the ledger's own
  `GET /events?until=<date>` means its START: recompute a pack's figure with
  its printed query (which carries the normalised bound), not the raw date.
- The lifecycle rows are sweep events, not findings: under a daily A1
  schedule one flagged agent is one event per day. The distinct rows
  de-duplicate within the window only.
- The canary exclusion is by the four exact ids; `test_canary_ids_are_exactly_the_estate_probes`
  fails if `tools/estate_probe.py` changes them. The retention note's
  "none among N resolvable manifest(s)" is the ledger's count and can
  include canary manifests.
- Retention is estate-level: the two retention metrics compare one estate
  policy with each manifest's floor; they do not say any agent's data was
  purged or kept.
- The signing key is whatever file the signer passes; this service neither
  stores it nor knows who holds it. The fingerprint identifies a key, it does
  not make the key trusted: `attest verify` needs the signer's public key
  from somewhere the verifier trusts.
- **Never reuse the pack-signing key for any other FIELD signing verb.** The
  signature is not domain-separated: its bytes are the same canonical JSON
  that `fedbroker sign --manifest` signs for any mapping, so a board-pack-shaped
  mapping signed that way with the same key verifies as a board pack. `attest
  verify` refuses a validly signed object that is not a `BoardPack`, which
  stops an ordinary manifest, not a crafted one. (Separating the domains means
  changing the signed bytes the plan fixes; not done.)
- Integrity BROKEN depends on the ledger reporting the break. A running
  ledger reports an unparseable record as a break (`/verify` 200 `ok: false`),
  which this pack shows as BROKEN. A ledger process restarted on an open
  segment holding such a record does not start, so the pack shows integrity
  unavailable (`ledger unreachable`). Any other non-verification answer
  (500, 404, ...) is shown as unavailable, "chain NOT verified; investigate".
- PDF depends on a local Edge/Chrome; absent one, HTML only (stated in the
  output, resolves STATE.md OQ-3 as best-effort).
