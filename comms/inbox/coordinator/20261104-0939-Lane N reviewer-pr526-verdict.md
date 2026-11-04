# Reviewer: PR 526 (scout S-D4) docs/IMPLEMENTATION.md section 2 matches CI's install and test steps

**Verdict: PASS WITH CONDITIONS on head `a219acbebe97567fb6a20fe1f2b9a1ff3e4ce068`.** Head unchanged at start and end; base current main (diff vs origin/main is the PR's own 2 files); 1 commit, Don Hagell noreply on author and committer. Docs plus one pin test. Not built by this lane.

Diff (HIGH, read): `docs/IMPLEMENTATION.md` +10 (retro install line, retro test command, `pytest -q tools/tests`, a "subset" paragraph naming three CI-only gates) and `tools/tests/test_implementation_guide_matches_ci_sd4.py` (+47, 6 tests).

## Claims checked against ci.yml on main (HIGH, read of the file)
The `tests` job holds: install of `defence-shield/agent-incident-retro` with `--no-deps -e`, `bash plugins/field-agent/verify_sync.sh`, `pytest -q tools/tests`, `python tools/topology_lint.py`, `python tools/environment_anchors.py --check`, and `(cd defence-shield/agent-incident-retro && python -m pytest -q tests)`. Every command the PR adds is in the job, and the three gates it names as CI-only are exactly the three the guide does not repeat. The subset claim is true.

## Objections first
1. A pin test that only greps strings proves the words exist, not that a reader can run them: a command correct as text but wrong in order or directory passes.
2. The guide is a mirror of CI that can drift again; the pin test reads ci.yml for three premises, so a CI change fails it (intended).
3. The guide still omits the field-core and sealed-ledger test line of the same job; not claimed by this PR (not checked here whether section 2 lists it elsewhere).

## Measured (GX10 ~/ff-work/wt-ln526, python -B)
New file 6 passed. CI at read: 7 checks with no conclusion yet (pending), not 7/7. 16-suite not applicable to a docs change; light run only.

## Mutants (24 rows on IMPLEMENTATION.md; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| D1 section 2 installs the retro package | 4 | 0 |
| D2 section 2 runs the retro tests | 4 | 0 |
| D3 section 2 runs the tools tests | 4 | 0 |
| D4 the note says "subset" and that ci.yml wins | 3 | 1 (gap: the sentence "When the two differ, ci.yml wins" can be removed) |
| D5 the note names the CI-only gates | 3 | 1 (equivalent: the test matches the token `verify_sync`, not the "vendored-template" wording) |
| D6 the guide still calls ci.yml authoritative | 3 | 1 (INVALID: my mutant `non-authoritative list is` still contains the pinned substring) |
Totals counted from the table: killed 4+4+4+3+3+3 = 21; survived 0+0+0+1+1+1 = 3; 24 rows. 1 gap, 1 equivalent, 1 invalid.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (all 7 had no conclusion when I read).

## Findings (non-blocking; new PR only)
- F-526-1 LOW: pin "ci.yml wins" (D4).
- F-526-2 INFO: a test that executes nothing: consider whether `pytest --collect-only` per listed command would catch a wrong directory (objection 1).
