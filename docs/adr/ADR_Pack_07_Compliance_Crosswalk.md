# ADR Package — Compliance Crosswalk Engine (Initiative #7)

**Spin State Labs · Force-Field platform · Status: design record, pre-build · 2026-08-29 · MIT**
System: maps every FIELD manifest to OSFI E-23, EU AI Act, ISO/IEC 42001, and NIST AI RMF control requirements, and generates the evidence pack on demand when the regulator or auditor asks. Buyer: CCO/GC. Regulatory timing: OSFI E-23 effective May 2027; EU AI Act Annex III high-risk obligations December 2, 2027 (post-Digital-Omnibus — verified 2026-08-29).
*When committed to `docs/adr/` in SpinStateLabs/Force-Field, this record supersedes the build brief's System 3 section.*

## ADR 1: The Model Decision

**Context.** Two jobs: (a) maintaining the clause→control mapping between FIELD manifest structures and framework controls; (b) generating evidence-pack prose from a specific manifest against that mapping. Simplest class considered: a hand-authored static crosswalk matrix — no model at all. For a small number of frameworks it is not only sufficient, it is superior: every mapping is human judgment, reviewable and signable. It stops being sufficient at clause-population scale and for proposing mappings on novel manifest structures.

**Decision.** The authored matrix is the sole source of truth; an LLM proposes *candidate* mappings for unmapped clauses and drafts evidence-pack prose from matrix plus manifest — always suggestion-only, always behind a human sign-off gate.

- *Bias–variance:* a wrong mapping is a false assurance to a regulator — the costliest error this system can make — so the low-variance authored matrix carries the load, and the flexible, higher-variance generative capacity is confined to suggestions and drafting where a human intercepts every output.
- *Vendor exposure:* suggestion/drafting model is prompt-defined and switchable; the matrix — the actual asset — is vendor-free YAML.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| LLM maps everything, human spot-checks | Rejected: spot-checking inverts the assurance burden | A missed wrong mapping becomes a signed false claim |
| Fully manual forever | Rejected: does not scale past two frameworks or ten clients | The product stays a consulting engagement |
| **Chosen: authored matrix + gated suggestions** | Human judgment where it is load-bearing, model labour where it is cheap | Commits us to matrix stewardship and a suggestion-review workflow |

## ADR 2: The Decision & Measurement Design

**Context.** Output: a mapping table, a gap list, and a drafted evidence pack. Action triggered: the gap list drives remediation; the evidence pack goes to a named human whose **signature is the action** — the system itself never asserts compliance.

**Decision.**

- *False positive:* a control claimed satisfied when it is not — false assurance. Discovered by an auditor or regulator, it is close to existential for a governance vendor. This is the error the whole design bends to prevent.
- *False negative:* a gap flagged that is not real — wasted remediation effort and an over-conservative posture. Annoying, survivable, and visible in review.
- *Optimization:* hard against false positives. Suggestions carry a precision floor; anything below it renders as **"unmapped — review required,"** never as a mapping. The conservative default is a first-class output, not a failure state.
- *Metric:* human-reviewed suggestion precision on a golden set, and gap-detection recall — not raw accuracy, because mapping classes are wildly imbalanced and "unknown" is a legitimate answer that accuracy arithmetic punishes.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Recall-optimized suggestions | Rejected: floods reviewers with weak candidates | Review fatigue → rubber-stamping → the FP we fear |
| No suggestions, matrix-only | Rejected: novel manifest structures stay unmapped indefinitely | Coverage stalls as the manifest population grows |
| **Chosen: precision-floor suggestions** | Accepted gap: golden-set precision may not match precision on genuinely novel clause types | Monitored by logging reviewer overrides as the drift signal |

## ADR 3: The Data & Grounding Decision

**Context.** Knowledge needed: the regulatory texts themselves (E-23, EU AI Act, ISO/IEC 42001, NIST AI RMF and its agentic profile), the FIELD manifests, and the authored matrix. Regulations are public but **versioned and moving** — the EU AI Act's high-risk deadline moved from August 2026 to December 2027 mid-stream, which is precisely the class of fact a trained model confidently gets wrong.

**Decision.** Retrieval over a *version-pinned* regulatory corpus plus the manifests; every mapping and every evidence-pack claim cites manifest clause, control ID, and the regulation version/effective date it was generated against.

- *Why retrieval:* citations are the product — an evidence pack that cannot point to the exact control text is not evidence. Corpus updates are a re-index with an effective date, not a retraining.
- *Currency and access:* a reg-version watcher marks affected mappings stale on any corpus update; packs always state their generation version. Client manifests ground only that client's packs (per-tenant isolation, as in the Sentinel).

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Rely on the model's trained knowledge of regulations | Rejected: training data ages; the 2026 Omnibus timeline change is the in-house case study | Confidently citing repealed deadlines in a signed pack |
| Whole-regulation context stuffing | Rejected: cost and cross-title noise at four frameworks | Degraded mapping quality exactly where nuance matters |
| **Chosen: version-pinned retrieval** | Citations with effective dates are the deliverable | Commits us to corpus versioning, a reg-watch process, and stale-flag plumbing |

## ADR 4: The Risk & Guardrail Decision

**Context — two most material risks.** (1) **Performance:** a confidently wrong mapping — the false-assurance failure described in ADR 2 — is this system's catastrophic error class. (2) **Control/Governance:** accountability for a signed pack must be unambiguous; a pack generated from a stale corpus or an unreviewed suggestion with no named signer is an audit finding waiting to happen. Lower priority here: security (read-only over public texts and internal manifests), societal, economic, ethical (no decisions about individuals).

**Decision.** The Crosswalk is generation-only, so the guardrail is the sign-off gate: nothing leaves the system without a named human signature; every claim carries its three-part citation (clause · control · version) so a reviewer can verify in one step; below-floor mappings render as "unmapped — review required" and are never silently dropped.

| Guardrail (one sentence) | A regulation-version change flags every affected mapping stale and blocks pack regeneration until each is re-reviewed; no pack ships without a named signer and full three-part citations. |
|---|---|
| Trigger, action, accountable role | Trigger: reg-version change detected, or any suggestion below the precision floor. Action: stale-flag / render as unmapped; block regeneration until re-review. Accountable: Founder & CTO (until a client CCO formally owns their pack). |

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Silent auto-refresh on reg changes | Rejected: semantic drift underneath a signed document | A pack whose meaning changed after signature |
| No version pinning | Rejected: unverifiable claims | Evidence that evaporates under audit |
| **Chosen: stale-flag + re-review** | Residual risk named: between reg publication and watcher detection there is a stale window | Bounded by watch cadence; window length is itself reported |

## Economics note (pre-build)

Matrix authoring is founder time (the expensive, load-bearing part). Suggestion/drafting inference is per-clause and modest; input length is the long-document kind, so retrieval scoping — not context stuffing — is what keeps unit cost flat. Roadmap position: built third, after the Gateway; timed so a working evidence pack exists inside clients' OSFI E-23 transition window (effective May 2027).
