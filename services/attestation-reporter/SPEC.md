# SPEC — attestation-reporter

**Purpose:** Render the governance board pack from live services in one
command: HTML + JSON (+ best-effort PDF), with every figure carrying the
literal query it came from. Ledger integrity leads the pack because every
other number stands on it.

**Exec owner:** CEO / board.

**FIELD letters:** all — this is the executive view over the platform.

**v0.1 scope**
- `attest serve` (:8013): `GET /health`, `GET /pack` (JSON), `GET /pack.html`
  — a windowed (`period` or `since`/`until`), ALWAYS unsigned draft; a bad
  window ⇒ 422.
- `attest render` CLI → `board-pack.{json,html,pdf?}`; `--period` (strict
  UTC quarter) or `--since`/`--until` (inclusive, UTC-normalised), neither ⇒
  all-time; `--signer NAME --sign-key PEM` signs `board-pack.json`
  (Ed25519 over the canonical dump without the `signature` key).
- `attest verify board-pack.json --pubkey PEM` (exit 0 valid; 1 unsigned,
  wrong key, altered, not canonical JSON — a duplicated key or
  NaN/Infinity — a re-spelled signature, or a signed object that is not a
  board pack).
- Every metric carries `basis`: `window` (ledger events inside the window;
  the query carries the bounds) or `point_in_time` (as at generation).
- Rule-7 canary agents: one "gate verification" row, excluded from every
  governance metric.
- Expirations & re-attestation: the 30-day token figure plus windowed
  lifecycle sweep-event counts and de-duplicated agent/token counts.
- `Metric` model enforcing: value ⇒ source_query; unavailable ⇒ no value
  (no fabricated zeros).
- Sections: integrity, agents, conformance (rate + raw counts with printed
  formula), enforcement, delegation, expirations & re-attestation (expiry
  horizon computed client-side, formula noted), federation & lifecycle,
  gate verification.
- PDF via headless Edge/Chrome when present (OQ-3 resolved as best-effort;
  HTML canonical).
- Adversarial tests: governor-down ⇒ unavailable; tampered chain ⇒ BROKEN
  leads the pack (a record the ledger cannot parse ⇒ a running ledger's
  `/verify` answers 200 `ok: false` ⇒ BROKEN; a `/verify` answer that is not
  a verification ⇒ integrity unavailable, "chain NOT verified", never
  "unreachable").

**Explicit non-goals (v0.1)**
- No time series / warehousing (archive the packs).
- No scheduling (pair with lifecycle-manager's scheduler).
- No signing of served packs — `attest serve` always returns an unsigned
  draft (F4 decides on an estate key); only the CLI signs, and only the JSON.
- No reconstruction of point-in-time figures (registry, tokens, escalations,
  integrity) for a past window.
- No LLM commentary — the pack is numbers with sources, full stop.
- No domain separation of the pack signature (the bytes are the plan's
  canonical dump, the same JSON canonicalisation other FIELD signers use):
  the pack-signing key must not be reused for any other signing verb.
