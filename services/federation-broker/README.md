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
| 5 | Requested scope ∈ contract `allowed_scopes` | `F.peer` BLOCK |
| 6 | Data class ∈ contract `allowed_data_classes` | `F.peer` BLOCK |

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
| The manifest the counterparty presents is *their real one* | **Declared only** | v0.1 has no signature/attestation on manifests — a counterparty can present a flattering document. Manifest signing is the known next step for F |
| The contract was actually signed by both GCs | **Declared only** | `contract_ref` points at the instrument; the broker records, it does not verify signatures |
| Traffic *content* stays inside the declared data class | **Declared only** | the broker gates the request envelope, not a payload inspection |

## LIMITS

- **The big one:** manifests are unsigned in v0.1, so step 1–3 verify
  *consistency*, not *authenticity*. The contract allowlists (steps 4–6)
  are the real gate — they are our record, not the counterparty's claim.
- One active contract per counterparty org.
- v0.1 gates inbound crossings; outbound gating (our agents calling out)
  mirrors this and is not yet wired.
- No API authentication in v0.1 — localhost trust (STATE.md OQ-1).
