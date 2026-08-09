# Hardening evidence — post-v0.1 backlog burn-down

**Date:** 2026-08-08 · **Tests:** 156 passing platform-wide (139 at the
12-system mark, +17 hardening)

## What shipped

**Inter-service authn (OQ-1 → resolved).** `field_core.authn`: shared-secret
`x-field-auth` middleware on all ten service APIs (`/health` stays open for
probes; `hmac.compare_digest`; secret read per-request from
`FIELD_SHARED_SECRET`). `auth_headers()` attached at every internal
httpx client and CLI call site — the external Anthropic upstream is
deliberately excluded so the internal secret never leaves the trust domain.
Unset secret = the documented localhost-trust demo mode, so demos and the
compose stack run unchanged. Every service README's OQ-1 LIMITS line moved
from Declared to Enforced-when-set; transport TLS remains a fronting-proxy
concern and stays Declared.

**Ed25519 manifest signing (federation top LIMIT → closed for keyed
contracts).** `field_core.signing` signs canonical manifest JSON; a
federation contract may now carry the counterparty's public key, and keyed
contracts require a valid signature on every crossing (new decision step 5).
Adversarial tests: missing signature, manifest tampered after signing, and
attacker-keyed signature all BLOCK; keyless contracts stay compatible and
their consistency-only nature stays in LIMITS. `fedbroker keygen | sign`
ship the operator workflow; key rotation/revocation is the named next gap.

**docker-compose verified on GB10 (OQ-5 → resolved).** Full stack built and
run on the DGX Spark (aarch64, Ubuntu 24.04, Docker 29 / Compose v5):
all nine services healthy, governed smoke flow correct end-to-end —
register 200, mint 201, sentinel **BLOCK `I.manifest`** (fail-closed, as
designed with no manifest in the container), ledger chain verifies. ~4 min
wall time. **Found defect:** the Dockerfile omitted federation-broker from
the pip install list — caught at runtime on GB10, fixed there and in the
repo. Netlify was evaluated and rejected for this job: it is a
static/serverless platform and cannot run containers. x86_64 compose run
remains pending (CI candidate).

**Regulation-text ingestion (OQ-2 → resolved for three of four
frameworks).** Citations restructured from TODO stubs to a grounded
`Citation` model — `cited` requires reference + source URL + retrieval
date; pending entries may carry **no** reference (validator + guard test
enforce). Verified 2026-08-08 and now cited where they genuinely map:

- **EU AI Act** (Reg. (EU) 2024/1689): Art. 12 Record-Keeping ¶1 → ledger
  controls; Art. 14 Human Oversight ¶1 and ¶4(e) — the "'stop' button or a
  similar procedure" text — → kill-switch and oversight controls. Verified
  via the AI Act Explorer mirror; EUR-Lex cross-check flagged as required
  before external publication.
- **NIST AI RMF 1.0** (official NIST AIRC): GOVERN 1.6 (inventory) →
  registry; GOVERN 1.7 (decommissioning), 2.1/2.3 (roles, executive
  accountability), 6.1/6.2 (third parties) → identity/federation/
  delegation; **MANAGE 2.4 (supersede, disengage, deactivate) →
  kill-switch**; MEASURE 3.1 (risk tracking).
- **OSFI E-23 (2027, effective 2027-05-01)** (official OSFI): Principles
  1.1, 1.2, 2.1 (enterprise model inventory), 3.1, 3.6 (monitoring +
  decommission) mapped to identity, federation, registry, and delegation
  controls.
- **ISO/IEC 42001**: paid standard, text not obtained — every entry is
  `pending-purchase` and the guard test makes citing it from memory a
  build failure.

Unmapped (control, framework) pairs are `pending-text` with a reason —
notably FC-E-02 (spend caps) matched nothing verified in any ingested text,
and it says so rather than stretching.

## Deliberately still open

- EUR-Lex cross-check of the two EU articles; ISO 42001 purchase + read.
- Signing-key rotation/revocation protocol; TLS (fronting proxy); CI
  matrix incl. an x86_64 compose run.
- Per-caller identity (the shared secret is perimeter authn, not identity).

---

# Round 2 addendum (2026-08-09) — ops-console + anchoring + registry events

**Tests:** 168 passing platform-wide (156 → +7 ops-console, +3 registry
events, +4 anchoring, minor consolidation).

**ops-console (:8011)** — the human's dashboard over the fleet. Client-not-
authority by construction: every button proxies the owning service, so a
console kill is attributed and ledgered identically to a CLI kill; operator
names are mandatory (422 otherwise); unreachable services render
unavailable, never as empty state; with the shared secret set, the HTML
shell stays open but every `/api/*` call is locked. Verified live in a
browser against a staged three-agent fleet — the dry-run harness returned
`BLOCK [D.scope]` through the real page code path.

**Ledger anchoring** — closes the full-history-rewrite gap in the honest
way: `ledger anchor` pins (chain length, head hash), optionally
Ed25519-signed; `verify --anchors` demands the live chain still contain
every anchored position. The adversarial test regenerates an entirely
self-consistent forged chain — plain `verify_chain` passes it; the anchor
exposes it as REWRITTEN. The README says plainly: an anchor on the same
disk protects against nothing — ship it off-box or publish to a public
chain (the record is one small JSON object; OpenTimestamps is the natural
next step).

**Registry events** — identity changes (`registry.registered`,
`registry.status_changed`, `registry.updated`) now land on the ledger when
one is configured, closing the oldest documented gap.

**CI** — `.github/workflows/ci.yml` mirrors the documented install/test
procedure (py 3.11–3.14 matrix) plus an x86_64 compose smoke replicating
the GB10 verification. Flagged UNTESTED until the repo has a remote.

**EUR-Lex** — cross-check attempted and honestly recorded as blocked: the
official CELEX document exceeds fetch-tooling limits (truncates in the
recitals). A human with a browser closes this in minutes.
