# federation-broker

Inter-org crossing gateway. A counterparty org's agent may exchange a
governed request with ours only if its **manifest** declares federation with
us and our **contract** (registered by the GC) covers the requested scope
and data class. FIELD letter **F** (Federation). Exec owners: **CIO / GC**.

## Decision sequence (first failing clause decides)

| # | Check | Clause on failure |
|---|---|---|
| 1 | Counterparty manifest is VALID (`field validate`) | `I.manifest` BLOCK |
| 2 | Manifest declares `isolated: false` | `F.isolated` BLOCK |
| 3 | Manifest lists our org in `allowed_peers` | `F.peer` BLOCK |
| 4 | We hold an active contract for that org | `F.peer` BLOCK |
| 5 | If the contract holds their Ed25519 public key: manifest signature present and valid | `F.peer` BLOCK |
| 6 | Requested scope ∈ contract `allowed_scopes` | `F.peer` BLOCK |
| 7 | Data class ∈ contract `allowed_data_classes` | `F.peer` BLOCK |

Every crossing verdict is a ledger event (`federation.allow|block`).

## API & CLI

`PUT /contracts/{id}` · `GET /contracts` · `POST /crossing` · `GET /health`

```
fedbroker add-contract FED-2026-001 --org "Borealis Example Corp" \
  --scope "exchange invoice status" --data-class "invoice metadata" [--ref gc-vault/...]
fedbroker crossing --org ... --agent-id ... --manifest their-manifest.yaml \
  --scope ... --data-class ...          # exit 0 ALLOW, 1 BLOCK
fedbroker serve [--port 8010]
```

Home org comes from `FIELD_ORG_NAME` (default "Spin State Labs").

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Invalid counterparty manifests never cross | **Enforced in code** | validity checked first; adversarial test presents an unsealed-ledger manifest with a flattering peer entry |
| Isolated counterparties never cross | **Enforced in code** | `F.isolated` |
| No contract / out-of-contract scope or data class ⇒ BLOCK | **Enforced in code** | contract store lookup + allowlists |
| Every crossing is a ledger event | **Enforced in code** (best-effort delivery) | `federation.*` events |
| Keyed contracts: unsigned or tampered manifests never cross | **Enforced in code** | Ed25519 verify against the contract-registered public key; adversarial tests cover missing signature, tampered manifest, and wrong key |
| The manifest is *their real one* (keyless contracts) | **Declared only** | a contract without a registered public key runs in legacy consistency-only mode — register the key to close this |
| The contract was actually signed by both GCs | **Declared only** | `contract_ref` points at the instrument; the broker records, it does not verify signatures |
| Traffic *content* stays inside the declared data class | **Declared only** | the broker gates the request envelope, not a payload inspection |

## LIMITS

- Manifest signing (`fedbroker keygen` / `sign`) provides *authenticity*
  only when the contract carries the counterparty's public key — keyless
  contracts still verify consistency, not authenticity. Key exchange is
  out-of-band (the GC receives the public key with the contract
  instrument); there is no revocation/rotation protocol for keys yet.
- One active contract per counterparty org.
- v0.1 gates inbound crossings; outbound gating (our agents calling out)
  mirrors this and is not yet wired.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
