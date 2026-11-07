# Don's authorization: set the Fly internal-secret hash (chat, 2026-11-07 ~15:30Z; recorded by the coordinator)

Source: Don's chat answer "Yes, authorize" to the question "Also authorize setting the Fly internal-secret hash (a secret set)?". Completes the open line in 20261107-1525-coordinator-don-authorizes-fly-4b-and-redeploy.md.

## What is authorised
The estate-deployer may set the Fly secret that carries FIELD_INTERNAL_SECRET_SHA256 (the hash of the internal secret, G22), after the Fly image that reads it is live (PR 867 merged on main and redeployed).

## Guardrails (unchanged)
- Machine-to-machine only: generate and set the value on the estate host (WIF or the clipboard-intake tool); never print, paste, echo or write the secret or its hash into chat, a report, a ledger row, a commit or a command line. A report states only that the secret was set and the G22-style check result.
- Verify with the G22-style check after setting; roll back on any dropped_* rise or canary failure.
- Still not given by this record: the GB10 Stage 3 go sentence, the live R-1 rehearsal, or any Stage 4b go sentence. Those remain Don's.
