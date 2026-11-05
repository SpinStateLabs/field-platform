# builder-6: rebuild of PR 628
Old PR 628 (head 93b9c327) -> new PR 800 https://github.com/SpinStateLabs/field-platform/pull/800, head 0c7bb682853ea67df132c325e06b7a4c50084693, base main 869cf2ed.
Clean cherry-pick of 3501390c (merge commit dropped); one new file packages/field-agent/tests/test_cli_verbs.py. Author+committer Don Hagell noreply. No .github changes.
Ran (PYTHONUTF8=1, absolute-sibling PYTHONPATH): test_cli_verbs.py 17 passed; field-agent suite 228 passed, 1 failed (test_canary_agent::test_the_process_never_exits_on_a_halt, subprocess ModuleNotFoundError field_agent under my Windows relative PYTHONPATH; env artefact, MEDIUM confidence, not touched by this PR).
Review requested.
