# COORDINATOR: Don's recorded acceptances and ruling (chat, 2026-11-06)
- E4 / P5: Don wrote in chat "P5 accepted by Don". The runbook E4 marker for Fly Stage 1 (fly-stage4a-log-only-runbook-2026-10-27.md) is SATISFIED by this record. E1 (GB10 Stage 3 clean >= 6 h) and E8 (flylib.sh STAGE4-AWARE) still stand.
- Key creation: Don wrote in chat "OK for key creation": the GB10 verifier key creation (svc-verifier, tasks/gb10-log-only-scripts/s1-verifier-keygen.sh) is authorized by Don.
- Ruling on the GB10 pre-guard (untracked manifests/ssl-fp-*.yaml): MOVE (never delete) the 11 untracked manifests/ssl-fp-*.yaml out of ~/field-platform into ~/field-backups/untracked-manifests-20261106/ before the redeploy, record the list and sha256 of each, and restore them after if they are needed (they are not tracked by main). Card B-DEP-gb10-guard still lands the durable fix.
- Install the staged G17 file when the redeploy runs, with rollback ready.
