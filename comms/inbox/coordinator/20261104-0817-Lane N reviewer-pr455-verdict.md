# Reviewer: PR 455 (C-1165, WP10) agent-incident-retro synthetic calibration corpus and its tests

**Verdict: PASS WITH CONDITIONS on head `93ee701ae140848f082d6aad11be4af1813211d5`.** Head unchanged at start and end (git ls-remote); 1 commit, Don Hagell noreply on author and committer; base 4f731ee9 (main is cd3b7690, not contained). Tests and docs only; not built by this lane. Sibling PR 454 (defence-shield half) has its own PASS (Q-100), not re-read here.

Diff (HIGH, read): `tests/corpus_c1165/{README.md,__init__.py,corpus.py}` and `tests/test_calibration_corpus_c1165.py` (+325, 4 new files). Against current main the retro `src/` is IDENTICAL to the PR tree (0 diff lines), so the PR tests the code that is on main; the only difference from main is these 4 added files, so it applies cleanly.

## Objections first
1. Granularity: "one step either side" uses steps of 1 (300 s, 20 requests) and 0.01 (CV 0.34/0.35/0.36). A threshold moved inside the step (CV limit 0.345) is invisible by construction (survivor below): the corpus pins to the step, not exactly.
2. The author's own finding is right and I confirm it from `clauses.py:221-227` (read): `S.cadence` only returns a hit and never a verdict by itself, so tuning cadence thresholds moves grades, not verdicts.
3. "Calibration" in the title is misleading for a corpus the README says is not real calibration; the README says so plainly and a test pins the sentence.
4. Determinism relies on `render()` having no clock or randomness; the tests assert equality of two renders, which catches randomness but not a value that varies across processes (only one process, e.g. `hash()` ordering).

## Measured (GX10 ~/ff-work/wt-ln455, relative PYTHONPATH, own venv with typer, python -B)
New file 42 passed. Retro suite: 270 passed, 1 failed (`test_cli.py::test_scan_is_deterministic_across_processes`, FileNotFoundError from a subprocess; the same failure exists on main and on PR 497's base, baseline). CI: 7 of 7 SUCCESS on this exact head (gh). 16-suite not run by me.

## Mutants (26 rows, applied to the code the corpus claims to pin; source restored, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 session gap 1800 s (one session or two) | 5 | 0 |
| B2 pivot and block-escalate window 300 s | 6 | 0 |
| B3 cadence floor 20 requests | 5 | 0 |
| B4 cadence CV limit 0.35 | 4 | 1 (limit 0.345: inside the 0.01 step, undetectable) |
| B5 corpus is synthetic and deterministic | 3 | 2 (an unused `random.random()` and `int(time.time()) % 1`, both no-ops: invalid mutants) |
Totals counted from the table: killed 5+6+5+4+3 = 23; survived 0+0+0+1+2 = 3; 26 rows. No pinned behaviour is unguarded; B5 has 3 effective kills.

## Conditions
- C1: GX10 16-suite 16/16 on a head containing main (the PR base is 4f731ee9; a rebase onto main is a clean add of 4 files).
- C2: none else blocking. CI is already 7/7.

## Findings (non-blocking; new PR only)
- F-455-1 LOW: add a determinism check across processes (hash of `render()` from a subprocess with another PYTHONHASHSEED).
- F-455-2 LOW: the cadence-never-a-verdict claim has a corpus actor but no test that asserts that CLEAR holds with the cadence thresholds at their extremes.
