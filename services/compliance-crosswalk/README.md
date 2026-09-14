# compliance-crosswalk

Mapping engine: FIELD manifest fields → OSFI E-23, EU AI Act, NIST AI RMF
and ISO/IEC 42001 (pending text purchase) control requirements, with a
coverage matrix (declared vs. **evidenced**), an evidence pack drawn from
live platform artifacts, and content-change detection of the cited source
pages (regwatch). Exec owners: **CCO / GC**.

## The citation rule (read this first)

A citation exists **only** if the referenced text was retrieved and
verified from a named source on a named date — every cited entry carries
`reference + source_url + retrieved`, and the module's `INGESTION_LOG`
records exactly what was read. Unverified mappings carry **no reference**
and are marked `pending-text`. A guard test
(`test_adversarial_no_ungrounded_citations`) fails the build on any
reference without a source. A compliance tool that invents citations is
worse than none.

Ingestion status (2026-08-08): **NIST AI RMF 1.0** Core subcategories and
**OSFI E-23 (2027)** principles verified from official sources; **EU AI
Act** Articles 12 and 14 verified via the AI Act Explorer mirror of
Regulation (EU) 2024/1689 (cross-check EUR-Lex before external
publication); **ISO/IEC 42001** is a paid standard — every ISO entry is
`pending-purchase` and can never be cited from memory. Mappings are
deliberately conservative — a sparse honest crosswalk beats a dense
invented one.

Control ids (`FC-*`) and control statements are Spin State's own words.

## API & CLI

`POST /crosswalk` `{manifest, agent_id?, sources?}` → coverage report ·
`POST /crosswalk/markdown` · `GET /controls` · `GET /frameworks` ·
`GET /staleness` (flags, windows, history, `last_check`) · `/health`
(`every` = the armed scheduler interval, 0 = off) ·
`POST /pack` `{signer, manifest, agent_id?, sources?}` → 200 `{markdown, pack}`
(markdown + json) / 422 blank or missing signer, unknown body key / 409 stale
corpus, with `{message, flags, affected_controls}` naming the flagged
framework(s) and the affected control ids ·
`POST /regwatch/check` (no parameters; any body is ignored) → always 200
`{checked_at, trigger, exit_code, frameworks: [...], flagged, unreachable}` —
see [regwatch](#regwatch--content-change-detection-d4).

The service is composed at `/crosswalk` (`FIELD_CROSSWALK_URL`, port 8008)
behind the proxy; `x-field-auth` applies to every route but `/health` when
`FIELD_SHARED_SECRET` is set.

**CLI stays the canonical path; `POST /pack` is a thin adapter over
`generate_pack`** — the same call the `crosswalk pack` CLI makes, with the
same rules (signer gate, stale block with no override). `manifest` is
REQUIRED in the body. The shared resolver landed in v1.2 B0
(`field_core.clients.resolve_manifest`), and the registry record carries the
`manifest_ref` it needs — but this service does not yet make that
registry-lookup-then-resolve call, so an `agent_id` alone still resolves to
nothing here. Optionality by `agent_id` is **not built**. It is a
plan-assigned D4 deliverable (A3: "optionality lands in D4 after the resolver
exists"; plan Decisions §2) that D4 shipped without — open, and put to the
plan owner to build (registry `manifest_ref` → resolver, 422 when
unresolvable) or to move.
`create_app(stale_store=None, fetcher=None, every=0)` is the injection seam —
`stale_store` defaults to `StaleStore()`
(`$FIELD_DATA_DIR/crosswalk_stale_flags.json`, the same file the `regwatch`
verbs write); `fetcher` defaults to regwatch's live https fetcher; `every`
arms the scheduler (never read from the environment inside `create_app`).

```
crosswalk run manifest.yaml [--agent-id ID] [--markdown report.md]
crosswalk pack manifest.yaml --signer NAME [--agent-id ID] [--out-md F] [--out-json F]
crosswalk frameworks
crosswalk regwatch check [--fetch]        # exit 0 unchanged / 3 changed / 2 unreachable
crosswalk regwatch check-file FW --file PAGE.html --fetched-by NAME [--url URL]
                                          # exit 0 baseline|unchanged / 3 changed / 2 refused
crosswalk regwatch status | set-stale FW --reason R | clear FW --reviewed-by NAME
crosswalk serve [--port 8008] [--every SECONDS]   # --every ⇐ FIELD_CROSSWALK_EVERY
```

With `--agent-id` (CLI) or `agent_id` without `sources` (API), live
evidence is collected: registry record, ledger `/verify`, per-agent event
counts, delegation tokens, governor cap. `sources` in the body, when given,
is used as-is.

## Coverage semantics

| Column | Meaning |
|---|---|
| **Declared** | The manifest states it (placeholders count as *not* declared) |
| **Evidenced** | A live platform artifact demonstrates it (✓/✗), or `—` if evidence wasn't collected |

Declared ≠ evidenced is the honesty line, in table form.

## ADR 07 delta — gated suggestions, evidence packs, reg-version staleness

- **Gated suggestions** (`CROSSWALK_SUGGEST=off|mock|anthropic`, default OFF;
  unrecognized → off): an LLM proposes *candidate* mappings for manifest
  paths the authored matrix doesn't cover (`crosswalk suggest <manifest>`).
  Precision floor (`CROSSWALK_SUGGEST_FLOOR`, 0.8): below-floor or errored
  suggestions render as **"unmapped — review required"** — a first-class
  conservative output, never a mapping, never dropped. Every entry carries
  "SUGGESTION ONLY — requires human sign-off; not a mapping". The authored
  matrix is the sole source of truth and is never mutated. The `anthropic`
  path requires a governor cap for `compliance-crosswalk` (self-manifest
  declares USD 5/daily) — no unmetered LLM calls.
- **Evidence packs** (`crosswalk pack <manifest> --signer NAME`): coverage
  table + gap list where every claim carries the THREE-PART citation
  (manifest clause · control ID · framework reference with retrieved date);
  pending-text / pending-purchase render as exactly that. **No pack without
  a named signer** — "Signature is the action — this system never asserts
  compliance; a named human signs, or nothing ships."
- **Reg-version staleness** (`crosswalk regwatch check|status|set-stale|clear`,
  `GET /staleness`, `POST /regwatch/check`): the corpus is version-pinned
  (`corpus-2026-08-08`); a stale flag on any framework — set by regwatch
  detection or by an operator — **hard-blocks pack generation** (exit 3, no
  override exists) until a NAMED human re-review clears it on the CLI
  (logged with reviewer + timestamp); the stale-window length is itself
  reported.

## regwatch — content-change detection (D4)

`regwatch.py` re-reads the pages the citations were verified against and
compares a sha256 of their **normalised text** with the last reading. It
detects **content change (normalised text), not semantics**.

- **Inventory, derived** from the mapping table (the distinct `source_url` of
  each framework's cited entries): OSFI E-23 (1 page, official), NIST AI RMF
  (1 page, official), EU AI Act as an ordered candidate list — the official
  EUR-Lex ELI URL `https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng`, then
  the two cited AI Act Explorer mirror pages (Art. 12, Art. 14). ISO/IEC
  42001 is an explicit `no-source` row (`pending-purchase`) and is never
  fetched. `Citation.source_url` is unchanged — it records what was read on
  2026-08-08; each reading records `via` (`official` / `mirror`).
- **Hash target**: visible text — script/style content, comments, tags and
  attributes (so `<meta>` tokens and nonces) stripped, entities unescaped,
  whitespace collapsed. `byte_diff` is still reported on the raw bytes.
- **Statuses** per source and per framework: `baseline` (first reading:
  hash stored, nothing flagged) · `unchanged` · `changed` (the framework is
  flagged with `mark` semantics — `StaleStore.apply_mark` inside the store
  transaction — reason = url + old→new sha256 prefixes + raw byte diff; a
  re-mark keeps `flagged_at`) · `unreachable` (non-200,
  timeout, off-https redirect, over 8 MB, no visible text, or `anchor
  missing` — the stored hash is untouched and it is **never** `changed`) ·
  `no-source`.
- **Anchored readings**: a 200 counts as a reading of a URL only if its
  normalised text names at least ONE reference identifier cited from that URL
  — derived from the mapping table (`Principle 1.1/1.2/2.1/3.6` for OSFI,
  `GOVERN 1.6 …`/`MANAGE 2.4` for NIST, `Article 12`/`Article 14` for the EU
  pages; the official EU URL takes both), whole-token and case-insensitive.
  A 200 bot-challenge / "verify you are human" page, soft 404 or moved page
  names none: `unreachable` with `anchor missing` — on the official EU URL
  that falls back to the mirrors. `regwatch check` (no `--fetch`) lists the
  anchors per URL.
- **Fallback**: when the official URL answers it is the reading; when it does
  not (403, timeout …) the mirrors are read, `fetched_via: mirror`, and the
  failed attempt is listed under `fallbacks`. Hashes are kept per URL, so
  switching between official and mirror is never a change.
- **Exit codes** (`regwatch check --fetch`; `exit_code` in the HTTP body):
  0 no NEW change and every needed source read · 3 a change flagged a
  framework on this run · 2 no new change but a needed source was
  unreachable. The exit code does **not** report a flag that was already
  standing (set by an earlier run or `set-stale`): exit 0 is "nothing new",
  not "all clear". Standing flags carry `flag_active: true` per framework,
  show in `regwatch status` / `GET /staleness`, and the CLI prints `STALE
  (standing): <framework>` on stderr whenever one stands. Without `--fetch`
  the CLI prints the inventory, anchors, stored hashes and `last_check` — no
  network.
- **Store**: the hashes are a `sources` key (and the last run a `last_check`
  key) in the same stale-flags file. Every write (`StaleStore.transaction`)
  takes a process-wide thread lock AND an OS exclusive lock
  (`fcntl.flock` / `msvcrt.locking`) on the sidecar
  `crosswalk_stale_flags.json.lock`, and holds both across RE-LOAD → change →
  persist. A named `clear` from the CLI — a separate process, e.g. `docker
  exec … crosswalk regwatch clear` — therefore either lands before a check's
  re-load or waits for its persist; it is never overwritten. A writer that
  cannot get the lock in 30 s raises (`StoreLockTimeout`) and writes nothing.
  Each persist writes its own uniquely named temp file, then `os.replace`.
  Scope: writers on one host sharing the file (one container, or one volume
  on one host) — advisory locks over a network filesystem are not claimed.
- **Egress**: `httpx`, timeout 20 s, redirects followed but every hop must be
  https (checked before it is sent), 8 MB cap, `User-Agent:
  field-platform-crosswalk/<version>`, and **no** `x-field-auth` or other
  platform header to third-party hosts.
- **Scheduler**: `crosswalk serve --every SECONDS` (`FIELD_CROSSWALK_EVERY`;
  compose and Fly default 86400) runs a check on a daemon thread, first tick
  after the interval, exceptions logged and swallowed. `last_check.trigger`
  is `scheduler` / `http` / `cli`.
- **Flags can be SET over authenticated HTTP, never cleared.** `POST
  /regwatch/check` can only mark; no route path contains a clear/unmark verb,
  `/staleness` is GET-only, and the clear is `crosswalk regwatch clear
  --reviewed-by NAME` on the CLI alone.
- **Tests are offline**: `tests/conftest.py` makes the default httpx client
  factory raise; one live test runs only with `CROSSWALK_LIVE_FETCH=1`.
- **Manual reading — `regwatch check-file`** (Don, 2026-09-13, for OSFI,
  which answers 403 to the honest User-Agent): a page a NAMED human saved
  from a browser goes through the same normalisation, anchor rule, compare
  and `apply_mark` as a fetch, in the same store transaction — `baseline` /
  `unchanged` / `changed` exactly as `check`, recorded against that URL with
  `via: manual:<NAME>`, `fetched_by` and the file's `file_sha256`. A fetch
  and a file of the same bytes are the same reading, so either can follow
  the other. `--url` is needed only for a framework watching more than one
  URL (eu-ai-act). Refused, nothing written (exit 2): a file that is not
  HTML (no `.html`/`.htm` suffix, no `<!doctype html>`/`<html` in the first
  64 KiB, or NUL bytes), an empty file, a file over 8 MB, a page that is not a
  reading (no visible text, or none of the URL's cited identifiers — a saved
  challenge page or the wrong page), an unknown or `no-source` framework, an
  unwatched `--url`, a blank name, a name with no letter or digit, or one
  carrying a control, invisible format (zero-width, BOM, bidi) or
  line/paragraph-separator character. It never clears a flag, does not touch
  `last_check` (that stays the record of the last automated check: after a
  manual OSFI baseline, `GET /staleness` still shows `osfi-e23` as the last
  automated result, e.g. `unreachable`; the manual evidence is the check-file
  report and the URL's stored reading, which `crosswalk regwatch check`
  without `--fetch` prints per candidate as `stored_via: manual:<NAME>`,
  `fetched_by` and `file_sha256`), and has
  **no HTTP route** (an upload would make the named human self-asserted by
  any holder of the perimeter secret).

### Manual OSFI procedure (check-file)

1. **Save.** Open the cited OSFI E-23 page in a browser and save it as HTML
   (Chrome/Edge "Webpage, HTML Only", Firefox "Web Page, HTML only"). If
   `check-file` answers `anchor missing`, the text was rendered by script:
   save again as "Webpage, Complete" and use its `.html`. Use the same save
   mode every time. Not MHTML, PDF or print-to-file. Keep the saved file: its
   sha256 is what the reading records.
2. **Copy to the estate.**
   - GB10: `scp osfi-e23.html gx10:/tmp/`, then on the GB10
     `docker cp /tmp/osfi-e23.html field-platform-crosswalk-1:/tmp/osfi-e23.html`.
   - Fly: `fly ssh sftp shell --app force-field-sandbox`, then
     `put osfi-e23.html /tmp/osfi-e23.html`.
3. **Run check-file in the crosswalk container**, as the human who saved it:
   - GB10: `docker exec field-platform-crosswalk-1 crosswalk regwatch
     check-file osfi-e23 --file /tmp/osfi-e23.html --fetched-by "<name>"`.
   - Fly (the ssh session does not run the entrypoint, so the data dir is
     given): `fly ssh console --app force-field-sandbox -C "env
     FIELD_DATA_DIR=/data crosswalk regwatch check-file osfi-e23 --file
     /tmp/osfi-e23.html --fetched-by '<name>'"`.
4. **Read the result.** Exit 0 `baseline` (first reading) or `unchanged`;
   exit 3 `changed` — the framework is flagged, packs are blocked until
   `crosswalk regwatch clear osfi-e23 --reviewed-by NAME`; exit 2 `REFUSED
   (nothing written)` with the reason. `STALE (standing)` on stderr names a
   flag that was already there.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| No fabricated regulation citations can ship | **Enforced in code** | adversarial guard test on the mapping table |
| Placeholder values never count as declared | **Enforced in code** | REPLACE-ME detection |
| Evidence verdicts come from real artifacts | **Enforced in code** | ledger verify / event counts / tokens / caps; broken chain ⇒ FC-L-01 ✗ |
| Below-floor suggestions never render as mappings | **Enforced in code** | floor gate + model validator refuses half-mapped candidates (tests) |
| The authored matrix is the sole source of truth | **Enforced in code** | suggestions cannot mutate CONTROLS (immutability test) |
| No pack ships without a named signer | **Enforced in code** | generate_pack raises on empty signer; CLI requires --signer — over HTTP too (test_pack_api.py) |
| Stale corpus blocks packs until named re-review | **Enforced in code** | StalePackError, no override parameter; clear requires --reviewed-by (tests) — over HTTP too (test_pack_api.py) |
| Every pack claim carries a three-part citation | **Enforced in code** | clause · control · reference+retrieved rendered per row (test) — over HTTP too (test_pack_api.py) |
| The mapping table is *correct* against each framework | **Declared only** | correctness of the mapping is exactly what ingestion + expert review must establish |
| Controls are *sufficient* for any framework | **Declared only** | coverage of our controls ≠ compliance with a regulation |
| Suggestion precision matches the golden-set floor on novel clauses | **Declared only** | mock proves the gate; reviewer-override logging is the drift signal once humans review |
| Content-change detection over the cited sources (the mechanism; live reach is the Declared row below) | **Enforced in code** | `regwatch.py`: normalised-text sha256 per URL; first reading = baseline (no flag); a differing hash flags the framework with url + sha prefixes + byte diff; re-mark keeps `flagged_at`; unreachable never `changed`; a 200 naming none of the URL's cited reference identifiers is `unreachable (anchor missing)`, never `changed` (`test_a_200_challenge_page_with_visible_text_is_unreachable_not_a_change`, `test_a_200_challenge_page_never_flags_or_blocks_packs`); official → mirror fallback reported; ISO never fetched; exit 0/3/2 — 0/2 mean no NEW change, standing flags named on stderr (`test_cli_check_names_standing_flags_even_when_it_exits_0`) (fake-fetcher tests, `test_regwatch.py`) |
| Regwatch checks never fetch in parallel (HTTP check vs scheduler tick) | **Enforced in code** | single-flight lock in `run_check` (`test_single_flight_a_second_check_fetches_nothing_until_the_first_returns`) |
| Stale flags can be SET over authenticated HTTP, never cleared | **Enforced in code** | `POST /regwatch/check` marks only; no clear/unmark route; `/staleness` GET-only; any body ignored (`test_no_http_route_can_clear_staleness`); 401 under the shared secret |
| A named clear is never overwritten by a check's write — same process or a separate CLI process, on one host | **Enforced in code** | thread lock + OS exclusive lock on `<flags>.lock` held across re-load → change → persist (`test_cli_clear_in_another_process_during_a_check_write_is_not_lost` runs the real CLI in a subprocess inside a check's transaction; `test_a_writer_waits_for_the_os_lock_and_times_out_loudly`; `test_scheduler_store_does_not_overwrite_a_named_clear`, `test_clear_during_the_fetch_window_survives_the_write`). Network filesystems: not claimed |
| Regwatch egress sends no platform credential and stays on https under 8 MB | **Enforced in code** | request hook on every hop, streamed cap, UA-only headers (`httpx.MockTransport` tests) |
| The interval scheduler fires and survives a failing tick | **Enforced in code** (in-process) | `serve --every` / `FIELD_CROSSWALK_EVERY` daemon thread (`test_served_scheduler_runs_a_check_after_the_interval`, `test_run_every_*`) |
| The real hosts answer httpx from CI / GB10 / Fly | **Declared only** (partial downgrade) | depends on network reachability outside the repo; the mechanism is Enforced with a fake fetcher, the live read is proven manually with `CROSSWALK_LIVE_FETCH=1`. First run (2026-09-13, build laptop): EUR-Lex ELI 200 (1.5 MB, `via official`), NIST 200, both mirror pages 200, normalised hashes identical across two reads — **OSFI 403** (see LIMITS) |
| A browser-saved page is read exactly like a fetch, named, and never clears a flag (`regwatch check-file`) | **Enforced in code** | `regwatch.check_file`: the same `normalise` / anchor rule / `_compare` / `apply_mark` inside `StaleStore.transaction`; `via: manual:<NAME>` + `file_sha256`; refuses not-HTML, empty, over 8 MB, not-a-reading, unknown/no-source framework, unwatched `--url`, a blank or no-letter-or-digit name, a name with Unicode control / format / line-separator characters — nothing written; `last_check` untouched, and the reading stays visible in `regwatch check` without `--fetch` (`stored_via`, `fetched_by`, `file_sha256`; `test_the_manual_reading_is_readable_later_while_last_check_keeps_the_automated_result`); CLI only, no route (`tests/test_regwatch_check_file.py`, incl. `test_a_file_hashes_exactly_like_a_fetch_of_the_same_bytes`, `test_fetch_and_file_readings_compare_against_each_other`, `test_check_file_has_no_http_route`) |
| A manual reading is the cited page as OSFI served it | **Declared only** | it proves only what the named human saved: nothing checks that the bytes came from the cited URL, or when (see LIMITS) |
| A flagged change is material | **Declared only** | content change (normalised text), not semantics — a named human re-review decides |
| The daily cadence actually ran on the estate | **Declared only** | proven only by `GET /staleness` `last_check` with `trigger: scheduler` later than start + interval on that estate |

## LIMITS

- It cannot say "you comply with X". It says which declared/evidenced
  controls map to the passages of X that were actually read (16/40 entries
  cited), and marks every other entry pending — ISO/IEC 42001 entirely.
- Evidence collection is point-in-time and best-effort (offline runs mark
  every control's evidence as not collected).
- FC-F-01 and FC-L-02 are declaration-only in v0.1 (no federation events
  until Phase 4; no retention enforcement).
- **OSFI refuses this client today.** The first live run (2026-09-13, from
  the build laptop) got HTTP 403 from the OSFI E-23 page for `User-Agent:
  field-platform-crosswalk/0.1.0`. regwatch does not disguise itself as a
  browser, so until OSFI serves this client every automated check reports
  `osfi-e23` `unreachable` (exit 2) and an OSFI change is **not detected
  automatically**. The OSFI reading is manual: a named human saves the page
  and runs `regwatch check-file` ([procedure](#manual-osfi-procedure-check-file)),
  or `set-stale`s on news. A change between two manual readings is detected
  only when the second one is taken — the cadence is the human's.
- **A manual reading proves only what the named human saved.** The file's
  bytes are whatever the browser wrote: nothing checks that they came from
  the cited URL, when they were saved, or that the name is who ran the
  command (`--fetched-by` is the operator's own statement, recorded as
  `manual:<NAME>`; the estate shell access is the control). Saves differ by
  mode: "HTML only" is the source as served, "Complete" is the page after
  scripts ran — mixing modes, or a first automated read after OSFI unblocks
  the client, can read as `changed` (a false flag a human clears by name).
  The saved file stays with the human; the store keeps its sha256, not it.
- regwatch watches **the pages that were read**, not regulatory activity in
  general. An amending act, a delegated act, guidance or a consultation
  published at another URL is not detected. The official EUR-Lex `/oj`
  rendering is the as-published Official Journal text — amendments arrive
  as separate acts and consolidated versions — so a change there is most
  likely a rendering change, not an amendment. Operators still `set-stale`
  on news the watch cannot see.
- Content change is not semantics, in both directions: a site redesign or a
  new banner reads as `changed` (a false positive a human clears by name),
  and a material change outside the normalised text (e.g. inside a linked
  PDF) is not seen.
- The anchor rule cuts both ways. A 200 challenge / soft-404 page that names
  none of a URL's cited reference identifiers reads `unreachable (anchor
  missing)` — no false flag. But a genuine rewrite that removes EVERY cited
  identifier from a page (a renumbered guideline, say) reads the same way:
  exit 2 and `anchor missing` on every run until the mapping is re-ingested,
  and it neither flags nor blocks packs — the operator `set-stale`s it. A
  rewrite that keeps any one cited identifier still reads `changed`. An
  interstitial that happens to quote a cited identifier is still read as a
  page (and would flag).
- Exit 0 from `regwatch check --fetch` means no NEW change. A cron that only
  tests the exit code (the workstation fallback below) cannot see a flag
  that is already standing — read `STALE (standing)` on stderr,
  `flag_active` in the JSON, or `regwatch status`.
- A named `clear` that arrives while a check holds the store lock waits and
  then clears the flag as that check left it — if the same check re-marked
  the framework, the history record of the clear carries the newer reason.
  The review is recorded against exactly what it removed.
- While the official EU URL is unreachable, the mirrors are read; a change
  only the official text carries is invisible until it answers again.
- Text is decoded as UTF-8 (undecodable bytes replaced); no charset sniffing.
- `POST /regwatch/check` performs live fetches on every call: the perimeter
  shared secret and a single-flight lock (one check fetches at a time; a
  second waits its turn, then fetches in full) are the only throttle.
- Daily egress from an estate to the four external hosts is an operator
  decision. `FIELD_CROSSWALK_EVERY=0` turns the scheduler off; `regwatch
  check --fetch` then runs from a workstation, but its hashes and flags land
  in THAT machine's `$FIELD_DATA_DIR` file — nothing syncs them to an
  estate, whose packs a workstation flag does not block.
- Matrix stewardship is founder time (ADR 07 economics): suggestions reduce
  the labour, they never replace the judgment.
- The real Anthropic suggester path is Declared-untested (no keys in CI);
  the deterministic mock proves the gate. Its routing is tested
  (`services/force-gateway/tests/test_d2_llm_callers.py`): base URL
  `FORCE_GATEWAY_URL` > `ANTHROPIC_BASE_URL` > default, with `x-force-passthrough: judge` +
  `x-field-auth` sent only to `FORCE_GATEWAY_URL` (v1.2 D2e). Routed through
  forcegw, the gateway's `ANTHROPIC_API_KEY` is the one used upstream; until
  Don places it (GB10 `.env`, Fly secret) forcegw answers 502 and a real
  suggester call fails. Suggestion quality stays Declared-untested.
