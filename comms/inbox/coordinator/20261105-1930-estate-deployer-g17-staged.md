# estate-deployer: G17 operators file built and staged (2026-11-05 ~19:30)

Authorized in chat by Don ("Yes, authorize"): verifier key creation on the GB10 and the `don` row ruling (scopes ["*"]).

- svc-verifier-gb10 key created ON the GB10: ~/.field-local/keys/svc-verifier-gb10/svc-verifier-gb10.key (0600, dir 0700). Never printed or copied. Hash fp 0779b3e8. [HIGH]
- Eleven-row file assembled from hashes only: don (rotated, fp 41bddfc7, scopes ["*"]), the nine other rows' existing hashes, plus the verifier. Assembler copy with the don row and "*" edited lives in the scratchpad; the shared `tasks/stage0-assemble-operators.py` table is NOT edited (it still carries the C-805-refused don row, a defect to fix there). file sha256 prefix b885ebdab2948f13. [HIGH]
- `operator_keygen.py --check` (main 3804d0b9, field_core loader): PASS, 11 active rows; assembler `--check` loader log-only and enforce PASS. [HIGH]
- Staged, NOT installed: GB10 ~/field-backups/operators-staging/operators-eleven-row.json (0600, hash matches). The live estate file is untouched; the running Stage 1 image (cefb81b) is not known to accept "*", so the install happens at the redeploy (atomic mv at re-arm). [MEDIUM]

Still blocked: GB10 redeploy needs a ruling on the untracked manifests/ssl-fp-*.yaml guard (blocker 3). Fly Stage 1 needs the E1/E4/E8 ruling (blocker 5). Stage 2/3 entries unmet (blocker 6). G27 untouched.
