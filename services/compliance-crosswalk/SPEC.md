# SPEC — compliance-crosswalk

**Purpose:** Map FIELD manifest fields to control-framework requirement IDs
and produce (a) a coverage matrix — declared vs. evidenced — and (b) an
evidence pack citing which live ledger/registry/delegation/governor
artifacts satisfy which control — over the CLI (canonical) and over HTTP
(`POST /pack`, a thin adapter that never asserts compliance: a named human
signs, or nothing ships).

**Exec owners:** CCO / GC.

**FIELD letter:** cross-cutting ("law" column of the platform).

**v0.1 scope** (as built through v1.2 D4)
- Static mapping table: 10 controls (FC-*) in our own words. Each entry for
  OSFI E-23, EU AI Act and NIST AI RMF is either `cited` — reference +
  source_url + retrieved, from text actually read on 2026-08-08 (16/40) —
  or `pending-text` with no reference; ISO/IEC 42001 (pending text
  purchase) is `pending-purchase` on every control. The anti-fabrication
  guard test fails the build on a reference without a source.
- `evaluate(manifest, agent_id, sources)`: declared check (placeholder-aware)
  + evidence check per control from injected `EvidenceSources`.
- CLI evidence collector hitting live services (registry, ledger, delegation,
  governor); offline runs report evidence as not collected.
- API: `/crosswalk`, `/crosswalk/markdown`, `/controls`, `/frameworks`,
  `/staleness`, `POST /pack` (evidence pack over HTTP: `{signer, manifest,
  agent_id?, sources?}` → `{markdown, pack}`; 422 blank signer, 409 stale
  corpus with affected controls — a thin adapter over `generate_pack`; the
  CLI stays the canonical path; `manifest` is required — resolving an
  `agent_id` alone through the registry + the B0 shared resolver is a
  plan-assigned D4 item (A3, Decisions §2) that is NOT built: open, with
  the plan owner), `POST /regwatch/check` (D4: read the cited sources now; always
  200 with per-source statuses; a change SETS a stale flag), and `GET
  /staleness` carries `last_check`. Composed at `/crosswalk`
  (`FIELD_CROSSWALK_URL`).
- regwatch (D4, `regwatch.py`): continuous content-change detection over
  the cited source pages — inventory derived from the mapping table, the
  EU AI Act read from the official EUR-Lex ELI URL with the cited mirror
  pages as fallback, ISO/IEC 42001 never fetched (`no-source`); sha256 of
  normalised text; first reading = baseline; unreachable is never a change;
  a reading must name at least one cited reference identifier of its URL
  (else `unreachable`, `anchor missing`); hashes in the stale-flags file
  (`sources`), every write under a thread lock + an OS file lock held across
  re-load → persist; exit 0/3/2 count NEW changes only. Scheduled in-process by
  `crosswalk serve --every SECONDS` (`FIELD_CROSSWALK_EVERY`). Manual path
  (Don, 2026-09-13; OSFI answers 403 to the honest User-Agent): `regwatch
  check-file FW --file PAGE.html --fetched-by NAME [--url URL]` reads a page a
  named human saved from a browser through the same normalisation, anchor
  rule, compare and flag, recorded as `via: manual:<NAME>` with the file's
  sha256; refuses a file that is not HTML, empty or over 8 MB (nothing
  written, exit 2); CLI only, no HTTP route; proves only what that human
  saved.
- CLI: `crosswalk run | frameworks | pack | regwatch (check [--fetch] |
  check-file | status | set-stale | clear) | suggest | self-manifest | serve
  [--every]`.

**Explicit non-goals**
- No citation from memory: a reference exists only for text retrieved from
  a named source on a named date; ISO/IEC 42001 stays pending-purchase until
  the text is bought and read.
- No compliance verdicts ("you comply with X") — coverage ≠ compliance.
- No semantic change analysis: regwatch detects that the normalised text of
  a cited page moved, never whether the change is material — a named human
  re-review decides, and only the CLI can clear a flag. Manifest evaluation
  stays point-in-time.
