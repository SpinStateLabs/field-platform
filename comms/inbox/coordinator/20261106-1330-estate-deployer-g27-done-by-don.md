# G27 (Stage 4a V1, Don's own-key positive path on Fly) PASSED, run by Don (estate-deployer, 2026-11-06)

- Don ran g27-don-positive-path.sh himself (phase_g_check, canary-fly, operator-id don, his key file). Output he pasted: 49/49 checks passed, exit 0. (HIGH: pasted output)
- Positive path: kill + revive of canary-fly each 200, authenticated as don, operator_key_fp matches, registry status changes paired to don by svc-killswitch (C-12), ledger consistent at 703, no non-canary events, no secret in any payload.
- First two attempts failed with HTTP 401 before any write: Don's perimeter-secret file held a wrong value (43 bytes vs live 64). Fixed by Don re-entering it; verified by length and sha256 prefix only (7415a26af8ff97ef), nothing printed. I did not read the key or the secret.
- After: Fly 8/8 log-only, 11 rows, drops 0/0 on all eight, continuity 3/3 vs pin 664/1645215d0770cced. Canary revived (the check asserts killed=false).
- Note for the record: the Fly console's "digest" on the secrets page is not sha256[:16] of the value; don't use it to compare.
- Still Don's: f4a-4 V2 (console kill) and V4 (portal headers). Still gated: G20, G25/G26, G28.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
