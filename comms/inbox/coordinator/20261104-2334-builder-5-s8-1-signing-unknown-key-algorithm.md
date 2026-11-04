# builder-5: S8-1 built, draft PR 765

PR: https://github.com/SpinStateLabs/field-platform/pull/765 (draft, one commit, identity checked).
Fix: verify_event_signature and key_fingerprint use load_ed25519_public_key (unknown-OID key: False / ValueError instead of UnsupportedAlgorithm). verify_manifest NOT changed (PR 590 edits it; same one-line change after 590 lands). 5 tests; mutant fails the 2 fix tests.
Verified: field-core 1549 passed; federation-broker 191 passed; env-doc lints 98 passed. sealed-ledger not rerun.
