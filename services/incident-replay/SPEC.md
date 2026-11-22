# SPEC — incident-replay

**Purpose:** Deterministic reconstruction of an incident window for one
agent from the sealed ledger, the registry, and delegation-authority:
who granted authority, what ran, which clause failed — rendered as a
structured post-mortem and RACI-ready markdown.

**Exec owner:** CISO.

**FIELD letter:** L — Ledger.

**v0.1 scope**
- `POST /replay` and `POST /replay/markdown` (agent id + ISO window; a
  date-only bound is refused with 422).
- Ledger `/verify` gate: reports on a broken chain carry an INTEGRITY
  FAILED banner and refuse to present events as trustworthy; a busy ledger
  (`ledger busy:`) carries INTEGRITY NOT VERIFIED — never OK.
- Authority = delegation grants overlapping the window (instants compared as
  datetimes); timeline = ledger events in window, at most
  `FIELD_REPLAY_MAX_EVENTS` (whole number 1..9999, default 5000, else the
  default, read per replay), the newest kept, a cut named in `integrity_notes`
  (`timeline truncated: showing the newest N of at least N+1 events; first_failure
  may be earlier than the window shown`), each summary cut at 300 characters with
  a `…[truncated n chars]` marker; first failure = first BLOCK/ESCALATE among the
  events read, enforced or log-only shadow (labeled); counts per type.
- RACI from data (C3): R registry owner; A from grant status at the first
  failure's timestamp — for D.expired/D.revoked the most recent covering
  grant that lapsed that way, else the earliest covering grant in force then,
  else the earliest overlapping grant; C the manifest's kill-switch
  `authorized_operators` when non-empty (blanks dropped); I the manifest's
  identity when not blank. Every
  party labeled with its source; fallbacks labeled `(default)`; manifest
  resolved via the field-core resolver (B0), reason reported.
- Integrity note when the window starts before the earliest live ledger
  event (C2 `/health` `earliest_live_ts` / `earliest_live_index`).
- CLI: `replay run | serve`; the CLI's service URL is `FIELD_REPLAY_URL`
  (default `http://127.0.0.1:8007`); the service reads `FIELD_LEDGER_URL` and
  `FIELD_DELEGATION_URL`.
- Adversarial test: on-disk trail edit ⇒ FAILED banner.

**Explicit non-goals (v0.1)**
- No LLM narration (a later, clearly-labeled optional layer).
- No cross-agent correlation or root-cause inference.
- No PDF (attestation-reporter owns board-grade rendering, Phase 4).
