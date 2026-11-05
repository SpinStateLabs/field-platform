# Review PR #775 (sealed-ledger: unknown-algorithm-OID keys are named refusals, S8-18) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `9d3016a13d3b2653fa752a38aaece4685d253af5` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 3 files: sealed_ledger/bundle.py (+6/-4), cli.py (+3/-2), tests/test_unknown_algorithm_key_s8.py (+151). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Four handlers gain `UnsupportedAlgorithm`: bundle._signer_public_pem, bundle._verify (supplied public key), cli._load_event_pubkey, verify-witness --pubkey. Messages now name the exception class, not its text (no new echo). Only adds refusals; no path became more permissive.
- Coverage of other sites (read on the head): api.py:211 `load_anchor_key` already catches UnsupportedAlgorithm; witness.tick catches NoAnchorKey, which wraps it; store.py uses field_core's load_ed25519_* helpers (already converted). I found no remaining unguarded site in sealed-ledger beyond what the PR lists. field_core.signing.key_fingerprint stays unguarded (PR reports it, out of scope).
- tests/test_unknown_algorithm_key_s8.py: 10 passed on the head (cryptography available in my env). Full sealed-ledger suite (PR: 812 passed) not run by me.

## Mutants (bundle.py / cli.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | UnsupportedAlgorithm dropped at _signer_public_pem | RED |
| M2 | dropped at _verify | RED |
| M3 | dropped at --event-pubkey | RED |
| M4 | dropped at verify-witness --pubkey | RED |
| M5 | signing-key message echoes `{exc}` | RED |
| M6 | verify message echoes `{exc}` | RED |
| M7 | _signer_public_pem catches bare `Exception` | SURVIVED |
Totals counted from the table: 7 mutants, 6 RED, 1 SURVIVED.

## LOWs (optional, new PR)
1. M7: nothing pins that an unrelated exception still propagates (a handler widened to `Exception` passes). Low value; note only.
2. Follow-up the author already names: make `field_core.signing.key_fingerprint` use `load_ed25519_public_key` so every caller is fixed once (needs its own card; `verify_manifest` callers unchecked by the author and by me).
