# attestation-reporter

One command renders the quarterly governance board pack from **live
services**: agents in production, conformance rate, blocks and escalations,
kill activity, expiring authorities, federation crossings, ledger
integrity. All FIELD letters. Exec owner: **CEO / board**.

## The rule: no number without a source

Every metric in the pack — JSON and HTML — carries the **literal HTTP query
it came from**, printed next to the value. The rule is enforced at the
model level: a metric cannot be constructed with a value and no source, and
an unreachable service produces an **`unavailable`** metric (query still
shown), never a fabricated zero.

## CLI

```
attest render [--out board-pack/] [--period "Q3 2026"] [--org NAME] [--pdf/--no-pdf]
```

Outputs `board-pack.json`, `board-pack.html`, and (best-effort)
`board-pack.pdf` via headless Edge/Chrome if one is installed — otherwise
it says so and ships HTML.

## What the board sees

| Section | Metrics (each with its query) |
|---|---|
| Ledger integrity | chain INTACT/BROKEN — the number the rest stand on, listed first |
| Agents | registered · in production · currently killed |
| Conformance | rate = ALLOW / all verdicts **incl. shadow**, plus five raw counts (allow/block/escalate + shadow_block/shadow_escalate — log-only would-blocks, labeled "not enforced") |
| Enforcement | kill activations · drills completed · open spend escalations |
| Delegation | tokens issued · expiring ≤30 d · revoked |
| Federation & lifecycle | crossings allowed/blocked · orphan escalations |

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every number carries its literal source query | **Enforced in code** | `Metric` model validator + test iterating every metric |
| Unreachable services show as unavailable, never zero | **Enforced in code** | adversarial test with the governor down |
| A tampered ledger surfaces as BROKEN in the pack | **Enforced in code** | integrity metric leads the pack; test tampers the chain |
| Derived figures show their formula | **Enforced in code** | conformance note prints `allows / (a+b+e+sb+se)` |
| A log-only estate cannot read 100% conformant | **Enforced in code** | shadow verdicts count in the rate denominator + own labeled rows (S2-R); adversarial test stages shadow events |
| The pack covers *everything the org runs* | **Declared only** | it covers what the platform governs; ungoverned shadow agents appear only via discovery/lifecycle findings |
| PDF fidelity | **Declared only** | best-effort headless print; HTML is canonical |

## LIMITS

- Point-in-time: figures are live queries at generation, not a warehoused
  time series — quarter-over-quarter trends need packs archived per quarter
  (store them; they're evidence).
- "All time" counts reflect current ledger retention; if the ledger is ever
  pruned, counts shrink with it (retention enforcement is future work).
- PDF depends on a local Edge/Chrome; absent one, HTML only (stated in the
  output, resolves STATE.md OQ-3 as best-effort).
- No API surface — deliberately a CLI you run and archive.
