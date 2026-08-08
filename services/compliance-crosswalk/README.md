# compliance-crosswalk

Mapping engine: FIELD manifest fields → control-framework requirements, with
a coverage matrix (declared vs. **evidenced**) and an evidence pack drawn
from live platform artifacts. Exec owners: **CCO / GC**.

## The citation rule (read this first)

v0.1 has **not** ingested the official texts of OSFI E-23, the EU AI Act,
ISO/IEC 42001, or the NIST AI RMF. Every framework citation is therefore the
literal stub `TODO-CITE-AFTER-INGESTION`. **No article or clause numbers are
asserted anywhere.** A test (`test_adversarial_no_fabricated_citations`)
fails the build if a real-looking citation appears before ingestion. A
compliance tool that invents citations is worse than none.

Control ids (`FC-*`) and control statements are Spin State's own words.

## API & CLI

`POST /crosswalk` `{manifest, agent_id?, sources?}` → coverage report ·
`POST /crosswalk/markdown` · `GET /controls` · `GET /frameworks` · `/health`

```
crosswalk run manifest.yaml [--agent-id ID] [--markdown report.md]
crosswalk frameworks
crosswalk serve [--port 8008]
```

With `--agent-id`, the CLI collects live evidence: registry record, ledger
`/verify`, per-agent event counts, delegation tokens, governor cap.

## Coverage semantics

| Column | Meaning |
|---|---|
| **Declared** | The manifest states it (placeholders count as *not* declared) |
| **Evidenced** | A live platform artifact demonstrates it (✓/✗), or `—` if evidence wasn't collected |

Declared ≠ evidenced is the honesty line, in table form.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| No fabricated regulation citations can ship | **Enforced in code** | adversarial guard test on the mapping table |
| Placeholder values never count as declared | **Enforced in code** | REPLACE-ME detection |
| Evidence verdicts come from real artifacts | **Enforced in code** | ledger verify / event counts / tokens / caps; broken chain ⇒ FC-L-01 ✗ |
| The mapping table is *correct* against each framework | **Declared only** | correctness of the mapping is exactly what ingestion + expert review must establish |
| Controls are *sufficient* for any framework | **Declared only** | coverage of our controls ≠ compliance with a regulation |

## LIMITS

- This is a crosswalk skeleton awaiting real texts — it cannot say "you
  comply with X"; it says "these declared/evidenced controls are the ones
  we will map to X once X's text is ingested."
- Evidence collection is point-in-time and best-effort (offline runs mark
  every control's evidence as not collected).
- FC-F-01 and FC-L-02 are declaration-only in v0.1 (no federation events
  until Phase 4; no retention enforcement).
