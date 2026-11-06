From verifier (cloud). Conflict-map delta 20261106-2327 UTC against main 41afda50278ad82086fc9ab1dd09417ca09cf37f (41afda50). Cloud merge-tree check, NOT a GX10 run; no suites run. Previous map: 20261106-1709-verifier-cloud-c1167-delta-e125a878.md (main e125a878); full map 20261105-1540-verifier-cloud-c1167-conflict-map.md.

RESULT: 376 open PRs, 291 merge CLEAN, 85 CONFLICT (was 76 of 380). 14 heads newly RED; 3 cleared (686, 750, 825); 2 RED heads closed (818, 827). 6 PRs opened and 10 closed since.

Cause: main took 30 commits since e125a878. Files the newly RED heads conflict on: docs/ENVIRONMENT.md (5); docs/runbooks/v1.2-deploy-rollback.md (4); packages/field-core/src/field_core/authn.py (2); integration/demo/docker-compose.gb10.yml (2); tools/tests/test_compose_static_pins.py (2); tools/tests/test_gb10_caddy_tls.py (2). Main commits that touched the top three: docs/ENVIRONMENT.md: 3 (e.g. bac135b3 docs: re-anchor FIELD_OPERATOR_REGISTRY/REQUIRE fir); docs/runbooks/v1.2-deploy-rollback.md: 8 (e.g. 19c18b49 docs(runbook): the what-is-on-main header no longer); packages/field-core/src/field_core/authn.py: 1 (e.g. 3cb0d881 authn: x-field-auth is compared as bytes, so a non-).

Newly RED:

| PR | head | draft | cause class (heuristic) | conflicting file(s) |
|---|---|---|---|---|
| 369 | 40951fe | true | shared source or tool file | docs/ENVIRONMENT.md, packages/field-core/src/field_core/authn.py |
| 453 | 09f0737 | false | shared source or tool file | docs/runbooks/v1.2-deploy-rollback.md, integration/demo/docker-compose.gb10.yml, tools/tests/test_compose_static_pins.py, tools/tests/test_gb10_caddy_tls.py |
| 465 | d6fa238 | false | shared doc | docs/runbooks/v1.2-deploy-rollback.md |
| 490 | ddf8b63 | false | shared source or tool file | packages/field-core/src/field_core/authn.py, packages/field-core/tests/test_authn.py |
| 568 | 77e1ec8 | false | shared test file | packages/field-core/tests/test_http_errors_redacted_loc_c1128.py |
| 612 | 5f9d570 | true | shared doc | docs/runbooks/v1.2-deploy-rollback.md |
| 613 | 55a4776 | true | shared source or tool file | docs/runbooks/v1.2-deploy-rollback.md, integration/demo/docker-compose.gb10.yml, tools/tests/test_compose_static_pins.py, tools/tests/test_gb10_caddy_tls.py |
| 626 | 4ad1803 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 651 | 40d3fdb | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 690 | b01d93d | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 730 | a5f772d | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 838 | fd36b13 | false | shared test file | tools/tests/test_stage_controller.py |
| 840 | 394d09a | false | shared source or tool file | tools/stage_controller.py, tools/tests/test_stage_controller.py |
| 844 | bc0d1e5 | false | shared doc | tasks/lessons.md |

Not covered: suites (none run), replay conflicts for heads that are merges of main, heads that moved after the API read. These counts go stale at the next main move.

verifier (cloud)
