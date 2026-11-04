# Report: S-C7 (scout round 3), builder. UNVERIFIED (cloud, no GX10). HIGH CARE: sealed-ledger.
Claim check: no branch or note for /export out_dir.
PR 522 (draft): https://github.com/SpinStateLabs/field-platform/pull/522, branch fix/export-outdir-nul-and-path-leak-sc7, head 480fd4ae28d8c07916d42896b793e59660ab3286 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A: sealed-ledger).
Bug (R, 5 red tests): out_dir with a NUL -> ValueError -> bare 500; the OSError handler answered detail=str(exc), i.e. the ledger host's absolute path in the response body. Fix: NUL -> 422 fixed text before any path work; OSError -> 500 "export failed (<ERRNO NAME>)". The armed (FIELD_OPERATOR_REQUIRE) branch with a NUL was NOT exercised (needs operator credentials); the NUL check runs before it.
Two mechanical knock-ons the repo's own lints required (both caught by tools tests, not by the sealed-ledger suite): docs/ENVIRONMENT.md 3 first-read rows (environment_anchors --fix), and tools/tests/boundary_echo_allowlist.txt `create_app.export::api-reply` 3 -> 2: the boundary-echo lint (C-505) saw that my change REMOVED one of the recorded debt sites. A lowered debt count, not a new allowance: coordinator may want to eyeball that line because it is a public-safety allowlist file.
7 tests; sealed-ledger 809 passed 5 skipped 1 error (test_operator_observer_c6_serve, "ledger serve exited early": baseline, identical on clean main); anchors/echo/proxy-lint/ci-anchors tools tests 267 passed; two mutants killed (1 red, 4 red).
Not run: other suites.
Overlap: PRs 500 (ledger NaN, also sealed-ledger api.py + docs/ENVIRONMENT.md) and 522 both touch docs/ENVIRONMENT.md and api.py; after either lands rebase the other and run `environment_anchors.py --fix`, do not hand-merge.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518, 519, 521, 522; none merged by me.
Round 3 not yet taken: S-C2, C3, C8; docs/CI S-D1..D8.
