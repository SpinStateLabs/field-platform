# Builder Lane 1: C-23 PR 291 ready (card C-450 exists); PR 288 findings acknowledged

## PR 291 (draft), card C-23
- Branch `ci/pin-deps-2026-10-28`, exact head `c13f2defd0a9131e9b0d651697da4889cf1bd609`, one commit on main 7e8f16e.
- Changed: `.github/workflows/ci.yml` (pip pinned to an exact version, `$C` = both constraints files on every `pip install`), new `integration/ci-constraints.txt` (pytest and three closure packages), new `tools/tests/test_ci_pip_pins_c23.py` (9 tests).
- Mutants (red/total): 7/7 inside the test file (pip upgraded, `$C` lost from each of three installs, `$C` naming one file, two floating pins).
- Before pushing: every pin in both constraints files has a wheel for Python 3.11, 3.12, 3.13 and 3.14 (`pip download --only-binary --python-version`). A CI-style install under both constraints files resolved on 3.13 (one pre-existing warning: claude-approver wants `anthropic`, installed with `--no-deps` as in CI today).
- Whole `python -m pytest -q tools/tests` on the head's tree: 2804 passed, 6 skipped, 0 failed (685 s, Python 3.13). That run started before I added the new test file, which passed alone (9 passed).
- NOT run: GX10 16-suite set (no GX10 tool in this cloud session). CI at the time of writing: 3 smoke jobs success; tests 3.11, 3.12, 3.13 and 3.14 still in progress. Read the conclusions, not the summary. This is the real check of the pins on every Python.
- Risk I could not remove: a pin that has a wheel but breaks a test on one Python only. If a tests job is red, I will fix on the same branch and say so with the new SHA.

## PR 288 (C-221): both C-446 reports read (PASS @19365c5; PASS WITH CONDITIONS, her tools-suite addendum pending)
Findings are LOW: F-C446-1 (a truthy non-boolean `hdrs("yes")` is held only by an anchor string; probe it) and `redirect: "error"` on the guarded writes (both reports), plus a pin that no window global holds the key. I will not touch the head (a PASS applies to its SHA). After PR 288 merges I will take them as one follow-up card if you queue it; propose title: "ops-console: guarded writes refuse redirects; hdrs(true) strictness and key-global pins (C-446 F-1/F-2)", files console.html + setup_harness.mjs + test_setup_behaviour.py, done-when: whole ops-console suite, mutants red.

## Next
Taking C-57 (httpx environment-proxy lint test, tools/tests) unless you assign another card.
