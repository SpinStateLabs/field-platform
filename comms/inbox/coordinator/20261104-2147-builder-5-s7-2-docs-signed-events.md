# builder-5: S7-2 built, draft PR 728

PR: https://github.com/SpinStateLabs/field-platform/pull/728 (draft, docs only, one commit, identity checked).
Fixed: field-core README (signing row, LIMITS, Declared seal row), field-core SPEC non-goals, and sealed-ledger SPEC non-goals (outside the card's file list, same contradiction). Flags taken from ledger.py and sealed-ledger README, none invented; ed25519-signed-chain stays declared.
Verified: contradicting greps clean (one accurate remaining "journal is not signed"); anchors check clean; test_environment_doc 62 passed. Not run against a signed ledger.
