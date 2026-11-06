# estate-deployer: blocker report 2 (2026-11-05 ~20:30 ET)

Don's chat ruling: "Ignore ssl-fp files". The GB10 tree guard no longer stops on them (a patched copy of gb10-deploy-stage0.sh with ALLOW_UNTRACKED widened to manifests/ssl-fp-*.yaml lives in the deployer scratchpad; the shared script is NOT edited). [HIGH]

## Done
- Stage 1 DISARMED on the GB10 (g6-rollback-v2, rehearsed rollback): .env equals the g1 backup, all eight services mode off, drop counters 0/0 on all eight both before and after, ledger continuity PASS (event_count 3386 >= pinned 2692, hash match), canary heartbeat advancing. Estate now at Stage 0 shape on build cefb81b. [HIGH]
- pg-run.py default ESTATE_SHA (14fed1ee) is stale: the first g6 run reported "health did not return" only because its gate demanded 14fed1ee while the estate runs cefb81b. The estate was fine; re-run with --sha cefb81b6e905eb1fa8ff7093fe057908dbda7ea3 passed. Fix the default (or have scripts read the live build) before any further pg-run use. [HIGH]

## Blocker 7: GB10 Stage 0 `pre` aborts
"running service set differs from the compose file's": `field-platform-approver-1` (image field-platform-approver:pilot-s2, started 2026-11-04T07:49Z) runs from an override file ~/field-backups/approver-pilot/docker-compose.approver.yml outside the checkout. Not mine, not in the compose set. I will not stop it or loosen the check without a ruling.
Ruling needed: tolerate the approver pilot (deploy must leave it running; `--force-recreate`/stop scope to be confirmed to exclude it) OR owner stops it first. Recommendation: tolerate, and confirm the up phase touches only compose-file services.

## Decision recorded
Estate left at Stage 0 (flags blank, canary clean), not re-armed on the old image: the eleven-row file (staged) is for the new image. Target SHA for the GB10 deploy: 3804d0b9 (matches Fly v18); origin/main has since moved to 25775af8.
