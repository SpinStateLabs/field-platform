# federation-broker

Inter-org crossing-decision service: it DECIDES whether a governed request
may cross the org boundary and ledgers the verdict; it does not carry the
traffic. Inbound, a counterparty org's agent may exchange a governed request
with ours only if its **manifest** declares federation with us and our
**contract** (registered by the GC) covers the requested scope and data
class. Outbound, our own agent is held to the mirror of the same rules
against the same contract. FIELD letter **F** (Federation). Exec owners:
**CIO / GC**.

## Decision sequence (first failing clause decides)

### Inbound (`direction: "inbound"`, the default)

| # | Check | Clause on failure |
|---|---|---|
| 1 | Counterparty manifest is VALID (`field validate`) | `I.manifest` BLOCK |
| 2 | Manifest declares `isolated: false` | `F.isolated` BLOCK |
| 3 | Manifest lists our org in `allowed_peers` | `F.peer` BLOCK |
| 4 | We hold an active contract for that org | `F.peer` BLOCK |
| 5 | If the contract holds their Ed25519 public key: manifest signature present and valid | `F.peer` BLOCK |
| 6 | Requested scope ∈ contract `allowed_scopes` | `F.peer` BLOCK |
| 7 | Data class ∈ contract `allowed_data_classes` | `F.peer` BLOCK |

### Outbound (`direction: "outbound"`) — our agent asks to cross out

| # | Check | Clause on failure |
|---|---|---|
| 1 | OUR manifest is VALID | `I.manifest` BLOCK |
| 2 | OUR manifest declares `isolated: false` | `F.isolated` BLOCK |
| 3 | OUR `allowed_peers` names the counterparty org (the same lenient case-insensitive substring rule the inbound check uses for our org) | `F.peer` BLOCK |
| 4 | We hold an active contract for that org — the SAME contract as inbound: one GC instrument covers both directions | `F.peer` BLOCK |
| — | *Signature step: SKIPPED.* The contract key is the counterparty's; it cannot verify our own manifest | — |
| 5 | Requested scope ∈ contract `allowed_scopes` | `F.peer` BLOCK |
| 6 | Data class ∈ contract `allowed_data_classes` | `F.peer` BLOCK |

The outbound verdict's `agent_id` is `<home_org>/<our agent>`; an ALLOW on a
keyed contract says in its reasons that the signature step was skipped.

### Request names per direction

| Field | Inbound | Outbound |
|---|---|---|
| `direction` | `"inbound"` (default) | `"outbound"` |
| `counterparty_org` | required — the org asking in | required — the org we cross into |
| `counterparty_agent_id` | required — their agent | optional — the peer agent called (recorded, not checked) |
| `counterparty_manifest` | required — their manifest | refused (422) |
| `manifest_signature` | required on keyed contracts | refused (422) — never checked outbound |
| `agent_id` | refused (422) | required — OUR agent |
| `manifest` | refused (422) | required — OUR agent's manifest |
| `scope`, `data_class`, `request_summary` | same | same |

Every crossing verdict is a ledger event (`federation.allow|block`) whose
payload carries `direction`; the verdict's `context` carries `direction`,
`home_org` and `counterparty_org`.

## API & CLI

`PUT /contracts/{id}` · `GET /contracts` · `POST /crossing` · `GET /health`

```
fedbroker add-contract FED-2026-001 --org "Borealis Example Corp" \
  --scope "exchange invoice status" --data-class "invoice metadata" [--ref gc-vault/...] \
  [--pubkey their-public.pem]          # PEM file or PEM text; exit 1 unless exactly one Ed25519 public key
fedbroker crossing --org ... --agent-id ... --manifest their-manifest.yaml \
  --scope ... --data-class ... [--signature B64]      # exit 0 ALLOW, 1 BLOCK
fedbroker crossing --direction outbound --org "Borealis Example Corp" \
  --agent-id invoicing-agent --manifest our-manifest.yaml --scope ... --data-class ...
fedbroker keygen [--out-dir DIR]  |  fedbroker sign --manifest m.yaml --key private.pem
fedbroker serve [--port 8010]
```

`--pubkey` is validated BEFORE any request as exactly one Ed25519 public key
PEM block — nothing before or after it but whitespace, so
`cat public.pem private.pem`, a trailing note or a second key is refused
(exit 1, nothing sent, the value never echoed). The same validator sits on
`FederationContract.counterparty_pubkey_pem`, so a raw `PUT` with a bad key
is a 422, and that 422 never quotes the request (`input` is dropped from
every validation error). The key is sent, stored and listed in canonical
PEM form. `add-contract` REPLACES a contract with the same id:
re-registering without `--pubkey` makes it keyless again.

Agents ask from code with the field-agent SDK (`FieldAgent.cross` /
`fieldagent cross`, `FIELD_FEDERATION_URL`) — the SDK asks this service; it
never relays traffic.

Home org comes from `FIELD_ORG_NAME` (default "Spin State Labs").

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Invalid counterparty manifests never cross | **Enforced in code** | validity checked first; adversarial test presents an unsealed-ledger manifest with a flattering peer entry |
| Isolated counterparties never cross | **Enforced in code** | `F.isolated` |
| No contract / out-of-contract scope or data class ⇒ BLOCK | **Enforced in code** | contract store lookup + allowlists |
| Every crossing is a ledger event | **Enforced in code** (best-effort delivery) | `federation.*` events |
| Keyed contracts: unsigned or tampered manifests never cross INBOUND | **Enforced in code** | Ed25519 verify against the contract-registered public key; adversarial tests cover missing signature, tampered manifest, and wrong key |
| A contract key is exactly one Ed25519 public key, and nothing else | **Enforced in code** | validated on write — CLI `--pubkey` exit 1 before any request, API 422 (`tests/test_federation_pubkey_cli.py`: garbage, PEM-shaped garbage, private key, X25519, truncated, blank, non-ASCII, a public key with a private key appended, with trailing text, with leading text, two public keys); only whitespace may differ from the canonical PEM, which is what is stored and listed; a row stored before this check still lists, and its inbound crossings BLOCK (never keyless) |
| A pasted private key is never quoted back or served to a lister | **Enforced in code** | the CLI error and the API 422 never quote the value (`input` dropped from every 422; `hide_input_in_errors` on the model); a legacy stored key containing a `PRIVATE KEY` PEM label lists as `<withheld: …>` and still fails closed (`test_legacy_row_holding_private_key_material_lists_withheld_and_fails_closed`) |
| Our invalid / isolated / off-peer manifests never cross OUTBOUND | **Enforced in code** | outbound mirror: `I.manifest` checked before the peer list or contract store is read (adversarial test), then `F.isolated`, `F.peer` (`tests/test_federation_outbound.py`) |
| Outbound: no contract / out-of-contract scope or data class ⇒ BLOCK | **Enforced in code** | the same contract lookup and allowlists as inbound |
| Every verdict and ledger event names its direction | **Enforced in code** | `context.direction` + ledger `payload.direction`; request fields of the other direction are refused (422) |
| Outbound: the manifest presented is the agent's real, registered one | **Declared only** | our agent presents its own manifest; the broker does not fetch the registry's `manifest_ref` or check that `agent_id` matches it. Outbound is not signature-checked (asymmetry above) |
| Outbound: an agent asks before it crosses | **Declared only** | cooperative — the broker decides what it is asked; an agent that crosses without asking is invisible to it |
| The manifest is *their real one* (keyless contracts) | **Declared only** | a contract without a registered public key runs in legacy consistency-only mode — register the key to close this |
| The contract was actually signed by both GCs | **Declared only** | `contract_ref` points at the instrument; the broker records, it does not verify signatures |
| Traffic *content* stays inside the declared data class | **Declared only** | the broker gates the request envelope, not a payload inspection |

## LIMITS

- Manifest signing (`fedbroker keygen` / `sign`) provides *authenticity*
  only when the contract carries the counterparty's public key — keyless
  contracts still verify consistency, not authenticity. Key exchange is
  out-of-band (the GC receives the public key with the contract
  instrument); there is no revocation/rotation protocol for keys yet.
- One active contract per counterparty org, and that one contract covers
  BOTH directions (one GC instrument). There are no direction-specific
  scopes.
- Outbound skips the signature step by design: a keyed contract holds the
  COUNTERPARTY's key, which cannot verify our own manifest. Outbound
  authenticity rests on our own registry/deploy controls, not on this
  service.
- The peer match is a lenient case-insensitive substring in both directions
  ("Borealis" matches "Borealis Example Corp (Canada)"). Outbound the needle
  is the request's `counterparty_org`, so the exact-name contract lookup
  that follows is what actually binds the org.
- A legacy contract row whose stored key fails the Ed25519 check (now
  including a valid key with other text around it) fails its inbound
  crossings closed; re-register it with `--pubkey` to fix it. It lists as
  stored, except that key text carrying a `PRIVATE KEY` PEM label is listed
  as `<withheld: …>`. Private material in any other shape (e.g. an unarmored
  secret appended to a legacy key) cannot be recognised and lists as stored.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
