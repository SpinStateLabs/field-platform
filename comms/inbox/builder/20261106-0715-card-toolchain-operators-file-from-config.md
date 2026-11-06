# Builder card: Phase G toolchain takes operators file path/hash/row set from config

Problem: `tasks/gb10-require-scripts/_lib.sh` hard-codes TEN_IDS, OPS_ROWS=10, STAGED=operators-ten-row.json and OPS_SHA16=ce5a9abcba8d2509. After C-805 the ten-row file is refused, so the eleven-row file (adds svc-verifier-gb10) needed a patched copy of the toolchain.

Ask:
1. Derive ids and row count from the staged file itself (jq/python), not constants; STAGED path from STAGE0_PG_STAGED (default operators-staging/operators.json).
2. OPS_SHA16 required via STAGE0_PG_OPS_SHA16 with no default (the pin must be the hex Don typed; a stale default is a footgun).
3. Fix cosmetic "ten"/"10 rows" strings and the BK copy name.
4. Also: gb10-deploy-stage0.sh `chmod 0644` mounted Caddyfiles after the ff-merge (umask 077 + proxy cap_drop ALL crash-loop), auto-capture unhealthy container logs in `up`, tolerate the approver pilot service, and update tasks/stage0-assemble-operators.py so `don` = ["*"] (C-805).
5. Dry-run transcripts regenerated for 11 rows.
Done = g0-g6 run unpatched against the eleven-row file on a fixture.
