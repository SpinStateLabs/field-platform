# fp-builder-b: B-S10-26 (reason half)
PR: https://github.com/SpinStateLabs/field-platform/pull/963 (draft). Head 0b8f08b004a46608996e7370d5da05718c1f198d, from origin/main; author and committer Don Hagell noreply (audited).
Scope: card's traceback half is open PR 600 (cli.py same lines); released once, dispatcher re-issued the card, so built only the uncovered --reason/--new-version rule.
Ran: new tests 20 pass (19 red before the fix); hand mutant (Cc only) 5 red; crosswalk suite 446 pass, 3 fail (test_staleness_fsync, same 3 on clean main, Windows); lints (boundary-echo, C-57, env-anchor, ci-anchor, docs-cite, env-doc) 314 pass.
Env note: the shared field-platform venv imports a different checkout; use a relative PYTHONPATH ('../../packages/field-core/src;src') or results are for the wrong tree.
Could not verify: GX10 16/16; full tools/tests (4 collection errors on this machine, not examined, and the full run exceeded 10 min).
Conflict: PR 600 also edits cli.py and docs/ENVIRONMENT.md (FIELD_CROSSWALK_EVERY anchor); second to land rebases and reruns environment_anchors.py --fix.
