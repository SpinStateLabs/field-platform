# Review PR 619 @ d2be5dbc7d687e6b017fa3fff2b4622c8df47f04 (rebuild of #414, B-11 vulture dead-code gate) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head d2be5dbc. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. A CI gate is only worth its wiring: a gate that is advisory, skipped, unpinned in version, or scanning half the tree passes every local test. Probed: 24 mutants, 7 on wiring.
2. vulture decides use BY NAME tree-wide at 80% confidence, so it misses an unused import whose name appears elsewhere; the gate is a floor, not a proof. The PR says so in its docstring (HIGH, read) and pins the claim.
3. The allowlist (6 entries) could rot or over-cover; both directions are tested (V9-V12 killed).
4. Windows host: the GX10 runs Git Bash (PROTOCOL); the backslash normalisation is unpinned (V15).

## Facts (HIGH)
- Head fetched via refs/pull/619/head = d2be5dbc; 7 commits; it contains origin/main 97dcfec1 (ancestor check passes), so it is rebased; author AND committer on all 7: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- Diff: `tools/vulture_gate.py` (+109), `tools/tests/test_vulture_gate_b11.py` (+279), `.github/workflows/ci.yml` (+8 -1), `integration/ci-constraints.txt` (+1, `vulture==2.16`).
- Ran the gate on the head: "vulture gate: clean (6 framework-signature entries allowed)", exit 0 (vulture 2.16 from the pin). Baseline unmutated: 24 passed.

## Mutants (the gate, ci.yml and the constraints file; the 24-test file each time; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| confidence threshold 80 (V1, V2) | 2 | 2 | 0 |
| exit codes: findings 1, vulture missing 2, no dirs 2, rc 3 = findings (V3-V6, V14) | 5 | 5 | 0 |
| scan both trees (V7, V8) | 2 | 2 | 0 |
| allowlist exact per (file, name), one finding per entry, stale reported (V9-V12) | 4 | 4 | 0 |
| findings reported and parsed (V13, V16) | 2 | 2 | 0 |
| path normalisation and clean message (V15, V17) | 2 | 0 | 2 |
| CI wiring: step advisory, continue-on-error, vulture installed and pinned (W2-W7) | 6 | 6 | 0 |
| CI step name (W1) | 1 | 0 | 1 |
Totals counted from the table: 2+5+2+4+2+2+6+1 = 24 rows; killed 2+5+2+4+2+0+6+0 = 21; survived 3; anchor failures 0.

## Survivors
- F-R619-1 LOW (V15): `replace("\\", "/")` on the finding path is unpinned; only matters on a Windows host (the allowlist keys use `/`).
- F-R619-2 LOW (V17): the clean line's entry count text is unpinned (cosmetic).
- F-R619-3 LOW (W1): W1 renamed the CI step title ("Dead-code gate (vulture ...)"); my mutant did not remove the step, it changed the name, so this row only shows the title is unpinned (the `run:` line is pinned by W2 and W5). I did NOT test removing the step entirely.
All three optional, NEW PR only.

## Not done
Whole `tools/tests` directory not run (only the PR's file and the gate itself). I did not run the gate against current main without the PR's allowlist change (the third commit drops three `redirect_request` entries; the head passes, so the drop is right for this tree).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head (CI installs vulture from the constraints file).
