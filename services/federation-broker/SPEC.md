# SPEC — federation-broker

**Purpose:** Decide inter-org agent crossings (a crossing-decision service;
it does not carry the traffic). Inbound: validate a counterparty's FIELD
manifest (valid, non-isolated, names us as a peer, signed when the contract
holds their key) and check the requested scope + data class against a
GC-registered federation contract. Outbound: hold our own agent's manifest to
the mirror of the same rules against the same contract. ALLOW/BLOCK with
clause ids; every crossing decision is a ledger event carrying its direction.

**Exec owners:** CIO / GC.

**FIELD letter:** F — Federation.

**v0.1 scope**
- SQLite contract store (`PUT /contracts/{id}`, one active per org);
  `counterparty_pubkey_pem` validated on write as exactly one Ed25519 public
  key PEM, nothing else but whitespace (422, never quoting the input), and
  stored in canonical form.
- `POST /crossing` inbound (default): seven checks, first failing clause
  decides (I.manifest → F.isolated → F.peer ×5: peer listed, contract held,
  signature when keyed, scope, data class).
- `POST /crossing` with `direction: "outbound"`: the mirror on OUR manifest
  (I.manifest → F.isolated → F.peer ×4: counterparty in our peers, contract
  held, scope, data class); the signature step is skipped outbound.
- `federation.allow|block` events with `payload.direction`; verdict
  `context.direction`.
- Home org via `FIELD_ORG_NAME`.
- CLI: `fedbroker add-contract [--pubkey] | contracts | crossing
  [--direction] | keygen | sign | serve`.
- Demo: two local "orgs" — Borealis's billing agent crosses into Spin State
  with an in-contract request (ALLOW), then over-reaches (BLOCK); our
  invoicing agent then asks outbound under the same contract (ALLOW,
  `context.direction: outbound`).
- Adversarial test: valid-looking peer declaration on an invalid manifest
  is blocked before the peer entry is read.

**Explicit non-goals (v0.1)**
- No authenticity for KEYLESS contracts: they verify consistency only.
  (Keyed contracts DO verify an Ed25519 manifest signature on every inbound
  crossing.) No key revocation or rotation protocol.
- No payload inspection; the envelope (scope + data class) is the unit.
- No signature check outbound (the contract key is the counterparty's), no
  registry cross-check of the outbound manifest, no multi-contract
  negotiation, no mTLS.
