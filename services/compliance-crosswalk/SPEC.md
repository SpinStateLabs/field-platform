# SPEC — compliance-crosswalk

**Purpose:** Map FIELD manifest fields to control-framework requirement IDs
and produce (a) a coverage matrix — declared vs. evidenced — and (b) an
evidence pack citing which live ledger/registry/delegation/governor
artifacts satisfy which control — over the CLI (canonical) and over HTTP
(`POST /pack`, a thin adapter that never asserts compliance: a named human
signs, or nothing ships).

**Exec owners:** CCO / GC.

**FIELD letter:** cross-cutting ("law" column of the platform).

**v0.1 scope**
- Static mapping table: 10 controls (FC-*) in our own words, each carrying
  `TODO-CITE-AFTER-INGESTION` stubs for OSFI E-23, EU AI Act, ISO/IEC 42001,
  NIST AI RMF. Anti-fabrication guard test enforces the stubs.
- `evaluate(manifest, agent_id, sources)`: declared check (placeholder-aware)
  + evidence check per control from injected `EvidenceSources`.
- CLI evidence collector hitting live services (registry, ledger, delegation,
  governor); offline runs report evidence as not collected.
- API: `/crosswalk`, `/crosswalk/markdown`, `/controls`, `/frameworks`,
  `/staleness`, `POST /pack` (evidence pack over HTTP: `{signer, manifest,
  agent_id?, sources?}` → `{markdown, pack}`; 422 blank signer, 409 stale
  corpus with affected controls — a thin adapter over `generate_pack`; the
  CLI stays the canonical path; `manifest` required until D4 wires the
  registry lookup into the shared resolver landed in B0). Composed at
  `/crosswalk` (`FIELD_CROSSWALK_URL`).
- CLI: `crosswalk run | frameworks | pack | regwatch | suggest | serve`.

**Explicit non-goals (v0.1)**
- NO regulation text, article numbers, or clause numbers — ingestion of
  official texts is a later session (STATE.md OQ-2), followed by populating
  citations with source-linked references.
- No compliance verdicts ("you comply with X") — coverage ≠ compliance.
- No continuous monitoring; point-in-time evaluation only.
