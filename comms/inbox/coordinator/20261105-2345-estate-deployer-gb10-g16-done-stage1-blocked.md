# estate-deployer: GB10 on ede21674 (G16 done with one manual fix); Stage 1 arming blocked on tooling (2026-11-06 ~03:30Z)

Rulings used: coordinator "tolerate approver pilot"; target = current origin/main.

## GB10 Stage 0 deploy
- Target SHA ede21674 (main with G23+G24; G21/G22 PRs 817/818 still open when I deployed; a later redeploy will be needed for them, which resets any clean window). Bare repo synced by gb10-sync.sh; patched copy of gb10-deploy-stage0.sh in the deployer scratchpad (shared script NOT edited): ssl-fp manifests tolerated, approver pilot excluded from project containers and `--remove-orphans` removed, SIGPIPE (exit 141) from `git log | head` under pipefail fixed. [HIGH]
- Attempt 1 (stage0-20261106b): `up` ran, 17 services healthy, the PROXY crash-looped; I rolled back (R1): continuity 3/3, mode off, counters 0/0, approver untouched. [HIGH]
- Attempt 2 (stage0-20261106c) with in-situ diagnostics: proxy exits 1 in ~140 ms, no log line. ROOT CAUSE (reproduced in isolation: "open /etc/caddy/Caddyfile: permission denied"): the deploy script runs with umask 077, so `git merge --ff-only` wrote integration/demo/Caddyfile and Caddyfile.gb10 as 0600 spinner; the target compose gives the proxy `cap_drop: [ALL]` (+NET_BIND_SERVICE), so container root has no CAP_DAC_OVERRIDE and cannot read them. FIX applied by hand: chmod 0644 on those two non-secret config files; the restart loop brought the proxy healthy within ~25 s. [HIGH]
- After the fix: `estate_probe health --expect-perimeter --expect-build-sha ede21674` 51/51 PASS; continuity vs pin 3421/546482d0a1a5a14b 3/3; all eight services mode off, drops 0/0, canary-gb10 running. [HIGH]
- Not recorded by the script: its `verify`/`canary` phases refuse (UP_DONE marker missing because `up` aborted at its health gate). I did not forge the marker; the checks above were run by hand with the same tool. The Stage 0 `canary` kill/restore sequence has NOT been run on this build. [HIGH]
- Added to the GB10 estate .env: `FIELD_GB10_LAN_IP=10.0.0.62` (runbook sec 8 precondition of the target compose; non-secret; before-copy in stage0-20261106b/env.before-lan-ip... see ~/field-backups/stage0-20261106/env.before-lan-ip). [HIGH]

## Defects to fix in the repo/tooling (not mine to edit unasked)
1. deploy script umask 077 + proxy cap_drop ALL = proxy cannot read 0600 Caddyfiles. Fix: chmod 0644 the mounted config after the merge (or umask 022 for the merge) in gb10-deploy-stage0.sh; any future deploy hits this again otherwise.
2. pg-run.py ESTATE_SHA default was stale; FIXED (default now reads the live killswitch build_sha).
3. gb10-deploy-stage0.sh up-phase has no auto-capture of non-healthy containers' logs/exit codes; add it.

## Blocker 8: Stage 1 (G18) cannot be armed by the existing tooling
The Stage 1 toolchain (gb10-require-scripts/_lib.sh, g0..g6-v2) is hard-wired to the TEN-row file: OPS_ROWS=10, TEN_IDS, STAGED=operators-ten-row.json, OPS_SHA16 pin ce5a9abc (the hex Don typed in the go sentence). Main refuses the ten-row file (C-805), so Stage 1 on this build needs the eleven-row file I staged (sha16 b885ebdab2948f13, ~/field-backups/operators-staging/operators-eleven-row.json). Overriding Don's hash pin and editing the guarded toolchain is a decision, not a fix. Needed: either (a) a coordinator/Don ruling to run a patched copy with OPS_ROWS=11, the eleven ids, the new STAGED path and OPS_SHA16=b885ebdab2948f13 (I can do this in the scratchpad), or (b) a v3 toolchain from the owner. Recommendation: (a), recorded here, Stage 1 stays LOG-ONLY and is one command to roll back.
Estate now: Stage 0 shape (flags blank) on ede21674. G27 untouched.
