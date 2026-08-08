# SPEC — compliance-crosswalk

**Purpose:** Map FIELD manifest fields to control-framework requirement IDs
and produce (a) a coverage matrix — declared vs. evidenced — and (b) an
evidence pack citing which live ledger/registry/delegation/governor
artifacts satisfy which control.

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
- API: `/crosswalk`, `/crosswalk/markdown`, `/controls`, `/frameworks`.
- CLI: `crosswalk run | frameworks | serve`.

**Explicit non-goals (v0.1)**
- NO regulation text, article numbers, or clause numbers — ingestion of
  official texts is a later session (STATE.md OQ-2), followed by populating
  citations with source-linked references.
- No compliance verdicts ("you comply with X") — coverage ≠ compliance.
- No continuous monitoring; point-in-time evaluation only.
