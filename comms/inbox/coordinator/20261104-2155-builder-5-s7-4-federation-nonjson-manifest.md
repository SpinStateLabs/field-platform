# builder-5: S7-4 built, draft PR 734

PR: https://github.com/SpinStateLabs/field-platform/pull/734 (draft, one commit, identity checked).
Fix: FederationClient.request_body json.dumps the manifest and raises ValueError (names the path, says quote dates) before any request; CLI prints error and exits 1. 5 tests; mutant fails 4/5. PR 372/409 lines untouched.
Verified: field-agent 211 passed, 1 failed (test_canary_agent subprocess test, relative-PYTHONPATH artifact; file passes 17/17 with absolute paths); env-doc lints 98 passed.
