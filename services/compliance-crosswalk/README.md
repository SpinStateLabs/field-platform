# compliance-crosswalk

Mapping engine: FIELD manifest fields → control-framework requirements, with
a coverage matrix (declared vs. **evidenced**) and an evidence pack drawn
from live platform artifacts. Exec owners: **CCO / GC**.

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
`GET /staleness` · `/health` ·
`POST /pack` `{signer, manifest, agent_id?, sources?}` → 200 `{markdown, pack}`
(markdown + json) / 422 blank or missing signer, unknown body key / 409 stale
corpus, with `{message, flags, affected_controls}` naming the flagged
framework(s) and the affected control ids.

The service is composed at `/crosswalk` (`FIELD_CROSSWALK_URL`, port 8008)
behind the proxy; `x-field-auth` applies to every route but `/health` when
`FIELD_SHARED_SECRET` is set.

**CLI stays the canonical path; `POST /pack` is a thin adapter over
`generate_pack`** — the same call the `crosswalk pack` CLI makes, with the
same rules (signer gate, stale block with no override). `manifest` is
REQUIRED in the body: nothing in the platform can resolve an `agent_id` to
a manifest until the shared manifest resolver exists; optionality by
`agent_id` lands after that (D4). `create_app(stale_store=None,
fetcher=None)` is the injection seam — `stale_store` defaults to
`StaleStore()` (`$FIELD_DATA_DIR/crosswalk_stale_flags.json`, the same file
`regwatch` writes); `fetcher` is held for the reg-watch fetch path and
unused today.

```
crosswalk run manifest.yaml [--agent-id ID] [--markdown report.md]
crosswalk pack manifest.yaml --signer NAME [--agent-id ID] [--out-md F] [--out-json F]
crosswalk frameworks
crosswalk serve [--port 8008]
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
- **Reg-version staleness** (`crosswalk regwatch status|set-stale|clear`,
  `GET /staleness`): the corpus is version-pinned (`corpus-2026-08-08`); a
  stale flag on any framework **hard-blocks pack generation** (exit 3, no
  override exists) until a NAMED human re-review clears it (logged with
  reviewer + timestamp); the stale-window length is itself reported.

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
| Reg changes are *detected* promptly | **Declared only** | detection is operator-fed in v0.1 (EUR-Lex fetch limits on record); the watch cadence bounds the stale window, and the window is reported |

## LIMITS

- This is a crosswalk skeleton awaiting real texts — it cannot say "you
  comply with X"; it says "these declared/evidenced controls are the ones
  we will map to X once X's text is ingested."
- Evidence collection is point-in-time and best-effort (offline runs mark
  every control's evidence as not collected).
- FC-F-01 and FC-L-02 are declaration-only in v0.1 (no federation events
  until Phase 4; no retention enforcement).
- The reg-version "watcher" does not watch in v0.1: staleness is marked by
  an operator or external process (`regwatch set-stale`). The enforcement —
  stale blocks packs until a named re-review, window length reported — is
  code; the detection cadence is a process commitment.
- Matrix stewardship is founder time (ADR 07 economics): suggestions reduce
  the labour, they never replace the judgment.
- The real Anthropic suggester path is Declared-untested (no keys in CI);
  the deterministic mock proves the gate.
