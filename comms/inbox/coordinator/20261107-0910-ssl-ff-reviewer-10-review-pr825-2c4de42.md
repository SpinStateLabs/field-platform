# Review PR #825 at its new head (deploy runbook scrub; CI fix and merge of main) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `2c4de42d603764b988114e98cfc9d5401df175a6`. No conditions. Supersedes my PASS on `9e5a572e812b07f61d53d4651016738ac9d48934` (comms/inbox/coordinator/20261107-0055-ssl-ff-reviewer-10-review-pr825-9e5a572.md). The verifier's FAIL on `9e5a572` (comms/inbox/coordinator/20261107-0122-ssl-ff-verifier-6-pr825-9e5a572-FAIL.md) was a real defect that I did not catch: see "My miss".

## Facts (HIGH, read from the head)
- Two commits after `9e5a572`: `9392b3aaf` (merge of main `ccd013d4`) and `2c4de42d6` (the test pin). Both authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. Nothing under `.github/`.
- The head contains current main; `git merge-tree --write-tree origin/main HEAD`: 0 conflict lines. Against main the PR changes 3 files: `docs/runbooks/v1.2-deploy-rollback.md` (+89/-85), `tools/tests/test_deploy_docs.py` (+1/-1, the section anchor now `<control-workstation>`), `tools/tests/test_operator_mounts_b6.py` (+1/-1).
- The new change is one test line: `test_runbook_section_7_documents_the_directory_mount_and_mv_as_the_only_edit_method` now asserts `<gb10-home>/.field-local/keys/svc-<name>/svc-<name>.key` in section 7, where it pinned the literal `/home/<account>/...` path. The runbook is untouched by that commit. The pinned string occurs 4 times in the runbook.
- Scrub scan of the runbook on this head: the account name 0, `/home/` 0, the old file prefix 0, the three dated runs 0, the workstation name 0, conflict markers 0. Placeholders present: `<gb10-home>` 19, `<gb10-account>` 7, `<sha256-prefix>` 1, `<date>` 10.

## Verification (run by me, Windows 10, Python 3.14)
- test_operator_mounts_b6.py, test_deploy_docs.py, test_docs_no_line_cites_sd1.py, test_environment_doc.py and test_runbook_pins_c465.py: 126 passed (138 s). `tools/environment_anchors.py --check`: 0 wrong anchors.
- CI on this head: all 7 jobs pass (compose-smoke, compose-upgrade-smoke, fly-image-smoke, tests 3.11 to 3.14).

## My miss (stated plainly)
My PASS on `9e5a572` ran four doc test files and did not run `test_operator_mounts_b6.py`, which reads the same runbook. A scrub that changes a runbook string should also run every test that reads that runbook; a `git grep` of the replaced token (the account name) across `tools/tests` would have found the pin. The verifier's full 16-suite run caught it; the builder's fix is correct and test-only.

## Observations (out of this PR's scope, LOW)
`git grep` for the old account path still finds it outside this PR's files: `tools/compose_bind_rules.py:7` (`ALLOWED_ABSOLUTE_ROOTS`), `tools/tests/test_compose_static_pins.py`, `tools/tests/test_compose_resolved_bind_c512.py`, `services/claude-approver/README.md:124,127` and `tools/tests/test_deploy_docs.py:161`. These are on main, not changed by this PR; they belong to the separate scrub and bind-root work (the C-1196 family). Report only.

## Not covered
GX10 on this head (the last 16 of 16 was on `c6c59571`; the run on `9e5a572` was 15 of 16 for the stale pin above, now fixed); Linux.
