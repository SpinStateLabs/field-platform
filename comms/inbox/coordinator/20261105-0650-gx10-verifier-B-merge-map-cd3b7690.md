# GX10 verifier B: merge-into-main map of the open PR heads on main cd3b76901f9aabfd45cee546f597177b8739d6ea (serves C-1140 and C-1167 in part; read-only, no GX10 suite run)

- Method: git merge-tree --write-tree main <head> in a scratch repo fetched from GitHub; heads read from refs/pull/<n>/head at about 02:40 EST; 89 open PRs. A clean merge is evidence of a clean merge only. Whole-PR merge, not a cherry-pick replay (C-1097 gap not covered). Cause classes not assigned and environment_anchors --fix not tried (I do not know which conflicts it would clear).
- Result: 65 CLEAN, 24 CONFLICT.

## CONFLICT (PR, head8, conflicting files, first 6)
- 479 760ff0cf: tasks/todo.md
- 474 4be156f6: tools/tests/test_422_handler_installed_c1114.py
- 457 85fa7d15: tools/tests/test_422_handler_installed_c1114.py
- 443 98fc9151: services/agent-registry/src/agent_registry/api.py,services/agent-registry/tests/test_d3_scan_hardening.py,services/federation-broker/src/federation_broker/api.py,tools/tests/test_422_handler_installed_c1114.py
- 425 186998a7: services/lifecycle-manager/src/lifecycle_manager/cli.py
- 416 0527401e: docs/ENVIRONMENT.md
- 411 896345e8: services/attestation-reporter/src/attestation_reporter/signing.py,services/attestation-reporter/tests/test_parse_verify_window_c1072.py
- 409 2c089ebb: docs/ENVIRONMENT.md,packages/field-agent/src/field_agent/liveness.py
- 408 45a9bee4: agents/ssl-invoicing-agent/SKILL.md,agents/ssl-timekeeping-agent/SKILL.md,manifests/ssl-timekeeping-agent.yaml
- 397 4128a3ac: agents/ssl-invoicing-agent/SKILL.md
- 395 740fd7d8: docs/ENVIRONMENT.md,services/federation-broker/src/federation_broker/engine.py,services/federation-broker/tests/test_org_normalise_c483.py
- 391 647786e2: tools/compose_bind_rules.py,tools/compose_resolved_check.py,tools/tests/test_compose_resolved_bind_c512.py,tools/tests/test_compose_static_pins.py
- 387 98de2c77: tools/compose_bind_rules.py,tools/compose_resolved_check.py,tools/tests/test_compose_resolved_bind_c512.py,tools/tests/test_compose_static_pins.py
- 385 112cf16d: tools/compose_bind_rules.py,tools/compose_resolved_check.py,tools/tests/test_compose_resolved_bind_c512.py,tools/tests/test_compose_static_pins.py
- 383 defb7eaf: docs/ENVIRONMENT.md,services/agent-registry/src/agent_registry/api.py,services/conformance-sentinel/src/conformance_sentinel/api.py,services/incident-replay/src/incident_replay/api.py
- 379 f958cab8: docs/runbooks/v1.2-deploy-rollback.md
- 372 1b8f9e3f: docs/ENVIRONMENT.md,packages/field-agent/src/field_agent/liveness.py
- 370 1381b565: tools/compose_bind_rules.py,tools/compose_resolved_check.py,tools/tests/test_compose_resolved_bind_c512.py,tools/tests/test_compose_static_pins.py
- 365 d570c31d: docs/ENVIRONMENT.md
- 355 640e1bd1: packages/field-core/tests/test_operator_auth_format2.py
- 352 6f306579: docs/ENVIRONMENT.md
- 344 22d04601: services/lifecycle-manager/src/lifecycle_manager/cli.py
- 342 82cae84e: STATE.md,agents/ssl-timekeeping-agent/SKILL.md,docs/IMPLEMENTATION.md,docs/runbooks/token-renewal.md,manifests/ssl-timekeeping-agent.yaml
- 326 da33a9a1: docs/ENVIRONMENT.md,packages/field-agent/src/field_agent/liveness.py,packages/field-agent/tests/test_bootstrap_errors_c503.py,packages/field-core/src/field_core/errors.py,packages/field-core/tests/test_upstream_error_c503.py,services/conformance-sentinel/tests/test_upstream_errors_c503.py

## CLEAN (PR head8)
489@53c30a02 488@b6675337 487@ce2876e4 486@06a242ed 485@1325e883 484@d43f7ec1 483@62b4d653 482@198afb11 481@043420cc 478@079e1b7d 475@19d14a49 473@07e0176b 472@07f8b40f 471@e222fc92 468@7f137163 467@ea8857b7 466@c00dc6c9 465@d6fa2389 464@b8ff923e 463@c0f781d4 462@057893c6 460@3040d198 456@77f0b8a2 455@93ee701a 454@616e01ed 453@09f07376 451@ac97f750 450@483e3f4b 449@ece150d7 445@307b1cf0 444@9e514a6e 441@56f2f1fa 439@68258586 437@355c3cac 436@b110353c 426@43294fc0 422@2fb120e4 421@849fdaef 420@e01094d1 419@93261b39 417@3e53c52b 414@2e066b77 410@4f9bf9b0 405@fc6b5492 400@a4294baa 399@653a4d45 398@3a936d9f 392@36c0d559 380@24d5482b 374@b97d35fc 371@13c91f54 369@40951fe6 368@37c19167 367@46bc0d9a 362@ef852435 360@c5fddb54 351@310c4099 346@64fc69f3 343@e5317342 340@25ffdc11 339@0219998a 316@3c769c7a 308@7f7ac748 297@3bb2510d 57@30ac1e11 
