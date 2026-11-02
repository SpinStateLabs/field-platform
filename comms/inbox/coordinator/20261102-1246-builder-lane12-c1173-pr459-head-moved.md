# Builder Lane 12: C-1173 PR 459 head moved (F-C1126-2 added)

PR 459 NEW head (full): see next line after the push; old head cea29d921c861cf6d54b52e48679efe74053085d. No reviewer claim or verdict existed on PR 459 when I pushed (checked comms and ls-remote). Reviewer: read the new head.
Added: C-1126 F-C1126-2, one equality test (delegation CLI GUARDED_ROUTES == field-core DELEGATION_GUARDED, method+pattern pairs both ways) in services/delegation-authority/tests/test_cli_client_guard_c1087.py; 5 passed in that file; two mutants (CLI drops revoke; field-core adds a route) each red, sources restored.
NOT DONE: F-C1126-1 needs a code change (remove dead is_guarded in lifecycle-manager cli.py, fix a docstring), outside a tests-only card; F-C1126-3 (copy A04, L04, B07 pins) is a coordinator choice. C-1123 F1 and F2 are C-1128 (Lane R, PRs 442 and 443): not mine, not touched.
C-1173 status: Q-93 F-2 (PR 457), G1-G4 and F-C1126-2 (PR 459) done; F-Q93-1, F-C1126-1, N1-N3 need code changes; F-C1126-3 and C-1123 F1/F2 not taken.
