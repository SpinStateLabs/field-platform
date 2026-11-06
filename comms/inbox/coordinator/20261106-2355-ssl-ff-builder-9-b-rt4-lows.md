# ssl-ff-builder-9: B-RT4-lows -> draft PR 864

PR: https://github.com/SpinStateLabs/field-platform/pull/864 (draft). Head ad6e75f739a545792aa9624794ed725fb423538c, one commit, author AND committer Don Hagell noreply; remote head verified equal to local.
F3 renew_token: new --verify-token-env (verifier reads RENEW_NEW_TOKEN_ID; {new_token} refused in that mode). Default placeholder mode unchanged, so cron lines still work; switching cron to the flag is a follow-up for Don.
F4 estate_probe: --allow-plaintext removed, docs updated. tools/phase_g_check.py has the same flag, not changed (not in the card): follow-up card suggested.
F5 operator_keygen --check: 16 hex (4 sites), pinned tests updated. The key-generation line `fingerprint:` still prints 8 hex via field_core key_fingerprint (not in the card).
TESTS one per item; MUTANTS 4 of 4 killed. Locally: keygen 65 pass, estate_probe rt4/check/cleartext 72 pass (2 fixture errors, services not on path), renew_token new 4 pass; full test_renew_token.py not run locally. CI not read yet.
Also: PR 858 (B-RT4 heartbeat) reported earlier. B-RT4-registry-manifest-ref-422-no-echo was already locked by another builder when I tried it.
