# Builder: service README drift card (docs only)

PR 560 (draft), branch docs/service-readme-env-routes-drift, head 20603775df52d98899257fb062d2cc0a379c0e1b, base main 97dcfec1. UNVERIFIED: no GX10, no CI.

Claim-check: no claim, PR or branch on service-README drift. PR 531 owns conformance-sentinel README/SPEC (not touched).

Found wrong (HIGH, re-read in code): line cites in services/lifecycle-manager/README.md (api.py 373-378 and 458-473 point at unrelated code; the isdigit/clamp lines are in create_app, last_tick is in the GET /findings route; cli.py:466 is a docstring), services/sealed-ledger/README.md (cli.py:881 is blank; --every is in witness_run). Fixed to symbols. compliance-crosswalk cites were still right, converted for the same reason.

Checked, no drift (HIGH): 16 env defaults and all route-table rows in the READMEs that have tables (differences are path-param names only). Env names in READMEs absent from service src (FIELD_ATTEST_URL, CLAUDE_APPROVER_SECRETS_DIR, FIELD_CROSSWALK_URL, FIELD_WITNESS_EVERY, FIELD_EXPORT_ROOT ...) are compose/CLI/other-service names, not drift.

Ran: environment_anchors --check (0 wrong); four lint test files 260 pass, 1 fail = known c57 baseline (PR 543). New test tools/tests/test_service_readme_claims.py 18 pass; mutants: every<0 -> every<-1 red, reinserted cli.py:447-452 cite red; both restored.

Not verified: prose claims (Enforced/Declared rows, "not implemented" lines) not checked row by row: not in source. No stale 'not implemented' found by grep (conformance-sentinel "Missing-write detection is not implemented" left alone, in PR 531's file).

Decisions needed: none. Review by someone other than the author.
