From verifier (cloud). C-1167 refresh and conflict map 20261105-1537 UTC. Cloud merge-into-main check, NOT a GX10 run; no suites run. Main used: 869cf2ed76e73d69a8a89df0d0e2aa83984064c6 (869cf2ed), re-read at fetch time.

Method: git merge-tree --write-tree --name-only origin/main <head> for every open PR head from the REST API (heads as of this read; a head that moves afterwards is not covered). A clean merge is evidence of a clean merge only: it says nothing about tests, and not about commit-by-commit replay.

RESULT: 368 open PRs. 320 merge CLEAN, 48 CONFLICT. Of the 48: 32 are drafts, 16 are ready for review (non-draft): 426, 443, 450, 457, 473, 474, 479, 481, 541, 556, 561, 600, 610, 639, 649, 676.

Cause classes (a heuristic from the conflicting file names and the PR base branch, not a reading of the hunks):
- anchors (docs/ENVIRONMENT.md only): 17
- shared source or tool file: 12
- shared doc: 10
- stacked: 5
- shared test file: 4

Most-conflicted files: docs/ENVIRONMENT.md (23); tools/compose_bind_rules.py (4); tools/compose_resolved_check.py (4); tools/tests/test_compose_resolved_bind_c512.py (4); tools/tests/test_compose_static_pins.py (4); packages/field-agent/src/field_agent/liveness.py (3); tools/tests/test_422_handler_installed_c1114.py (3); tasks/lessons.md (2).

Rebuild pairs (from the PR titles 'rebuild of #N'):
- Old PR conflicts, its rebuild merges CLEAN (12): 326 -> 547, 342 -> 797, 344 -> 550, 365 -> 727, 408 -> 557, 416 -> 565, 425 -> 564, 426 -> 617, 443 -> 568, 473 -> 609, 474 -> 792, 479 -> 579. Closing the old PR is the coordinator's call; I only report the status.
- Old PR and its rebuild BOTH conflict (2): 372 -> 556, 383 -> 561. These rebuilds need a rebase onto the current main.
- Both CLEAN: 28 pairs.

WP-mapped heads (mapping as in my 11-02 report plus the rebuild and batch PRs named in the queue):

| PR | what | status vs main 869cf2ed | conflicting file |
|---|---|---|---|
| 308 | WP8 Phase E words | CONFLICT | ROADMAP.md |
| 450 | WP8 rebuild of PR 308 (docs) | CONFLICT | docs/ARCHITECTURE.md |
| 368 | field-mcp PR 1 | CLEAN |  |
| 380 | field-mcp PR 2 | CLEAN |  |
| 57 | R4a rotator core (held) | CLEAN |  |
| 451 | WP7 Fly redeploy checklist | CLEAN |  |
| 797 | rebuild of PR 342 | CLEAN |  |
| 798 | rebuild of PR 400 (compose stack) | CLEAN |  |
| 799 | batch m3 (draft) | CLEAN |  |

PR 57 merges clean, but it is an old branch: its merge base with main is ad424103 of 2026-10-30, and main has moved 263 commits since. By commit id the branch carries 220 commits (217 non-merge) that are not on main; main is built from cherry-picked batches, so commit ids understate what has already landed by content. Clean does not mean current. PR 444 and PR 794 (named in earlier cards) are no longer open: merged or closed.

All conflicting heads:

| PR | head | draft | cause class | conflicting file(s) |
|---|---|---|---|---|
| 297 | 3bb2510 | true | shared doc | tasks/lessons.md |
| 308 | 7f7ac74 | true | shared doc | ROADMAP.md |
| 326 | da33a9a | true | shared source or tool file | docs/ENVIRONMENT.md, packages/field-agent/src/field_agent/liveness.py, packages/field-agent/tests/test_bootstrap_errors_c503.py, packages/field-core/src/field_core/errors.py, packages/field-core/tests/test_upstream_error_c503.py, services/conformance-sentinel/tests/test_upstream_errors_c503.py |
| 342 | 82cae84 | true | shared source or tool file | STATE.md, agents/ssl-timekeeping-agent/SKILL.md, docs/IMPLEMENTATION.md, docs/runbooks/token-renewal.md, manifests/ssl-timekeeping-agent.yaml |
| 344 | 22d0460 | true | shared source or tool file | services/lifecycle-manager/src/lifecycle_manager/cli.py |
| 352 | 6f30657 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 355 | 640e1bd | true | shared test file | packages/field-core/tests/test_operator_auth_format2.py |
| 365 | d570c31 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 367 | 46bc0d9 | true | shared doc | CHANGELOG.md |
| 370 | 1381b56 | true | stacked on test/compose-resolved-conditions-c638 | tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py, tools/tests/test_compose_static_pins.py |
| 371 | 13c91f5 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 372 | 1b8f9e3 | true | shared source or tool file | docs/ENVIRONMENT.md, packages/field-agent/src/field_agent/liveness.py |
| 379 | f958cab | true | shared doc | docs/runbooks/v1.2-deploy-rollback.md |
| 383 | defb7ea | true | shared source or tool file | docs/ENVIRONMENT.md, services/agent-registry/src/agent_registry/api.py, services/conformance-sentinel/src/conformance_sentinel/api.py, services/incident-replay/src/incident_replay/api.py |
| 385 | 112cf16 | true | stacked on test/compose-pr345-conditions-c715 | tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py, tools/tests/test_compose_static_pins.py |
| 387 | 98de2c7 | true | stacked on test/compose-resolved-realroots-c823 | tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py, tools/tests/test_compose_static_pins.py |
| 391 | 647786e | true | stacked on test/compose-static-nonstring-c817 | tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py, tools/tests/test_compose_static_pins.py |
| 395 | 740fd7d | true | shared source or tool file | docs/ENVIRONMENT.md, services/federation-broker/src/federation_broker/engine.py, services/federation-broker/tests/test_org_normalise_c483.py |
| 397 | 4128a3a | true | shared doc | agents/ssl-invoicing-agent/SKILL.md |
| 408 | 45a9bee | true | shared source or tool file | agents/ssl-invoicing-agent/SKILL.md, agents/ssl-timekeeping-agent/SKILL.md, manifests/ssl-timekeeping-agent.yaml |
| 409 | 2c089eb | true | stacked on fix/upstream-error-field-agent-c642 | docs/ENVIRONMENT.md, packages/field-agent/src/field_agent/liveness.py |
| 411 | 896345e | true | shared source or tool file | services/attestation-reporter/src/attestation_reporter/signing.py, services/attestation-reporter/tests/test_parse_verify_window_c1072.py |
| 416 | 0527401 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 425 | 186998a | true | shared source or tool file | services/lifecycle-manager/src/lifecycle_manager/cli.py |
| 426 | 43294fc | false | shared doc | CHANGELOG.md |
| 443 | 98fc915 | false | shared source or tool file | docs/ENVIRONMENT.md, services/agent-registry/src/agent_registry/api.py, services/agent-registry/tests/test_d3_scan_hardening.py, services/federation-broker/src/federation_broker/api.py, tools/tests/test_422_handler_installed_c1114.py |
| 450 | 483e3f4 | false | shared doc | docs/ARCHITECTURE.md |
| 457 | 85fa7d1 | false | shared test file | tools/tests/test_422_handler_installed_c1114.py |
| 473 | 07e0176 | false | shared doc | ROADMAP.md |
| 474 | 4be156f | false | shared test file | tools/tests/test_422_handler_installed_c1114.py |
| 479 | 760ff0c | false | shared doc | tasks/todo.md |
| 481 | 043420c | false | shared doc | tasks/lessons.md |
| 541 | 65ef470 | false | shared source or tool file | tools/start_role_session.py |
| 556 | c8792f8 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 561 | 24e0005 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 600 | b78674f | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 610 | 5f8ed98 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 639 | 179b147 | false | shared test file | tools/tests/test_volume_admin_trailing_newline.py |
| 649 | c0f5512 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 659 | 89d78b7 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 660 | 77b0dee | true | shared source or tool file | services/spend-governor/src/spend_governor/cli.py |
| 671 | 567d05f | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 676 | 24a9b94 | false | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 684 | 5dc8f0f | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 696 | 42d6d08 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 752 | 1eb8223 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 772 | 8f9b8aa | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |
| 784 | 9b1e503 | true | anchors (docs/ENVIRONMENT.md only) | docs/ENVIRONMENT.md |

Not covered: whole-suite results (none run), replay conflicts for heads that are merges of main (C-1097 method), heads that moved after the API read. Cloud run, Python not used here, nothing pushed to any PR branch.

verifier (cloud)
