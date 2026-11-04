# MERGE 21 (batch cb28: PR 459, commits 27bc1218 and c356e205 on main) - read-only fallback review, ssl-ff-reviewer-3

**FINDING SET (merged already, nothing to block): the pins are strong; 4 LOW survivors in the environment_anchors G3/G4 pins. UNVERIFIED (cloud, no GX10).** The mutants ran on a scratch checkout of origin/main 97dcfec1; nothing was pushed.

## Objections first
1. The commit message says each of G1-G4 has "a mutant that turns exactly one new test red"; the PR proves one mutant per gap, I probed four per behaviour.
2. G3 and G4 corner cases (indented comment, word boundary, partial path segment, Windows separator) are exactly where a later edit silently weakens the tool.
3. The delegation route-table test compares compiled patterns, so a rewritten but equivalent regex would fail it falsely (a maintenance cost, not a defect).

## Facts (HIGH)
- Both commits: author AND committer Don Hagell noreply (checked with `git show --format`). 27bc1218: +34 lines in `tools/tests/test_environment_anchors_c1116.py`; c356e205: +10 lines in `services/delegation-authority/tests/test_cli_client_guard_c1087.py`. Tests only.
- Baselines on main: anchors file 36 passed; delegation CLI guard file 5 passed.

## Mutants (the one test file each time; files restored; worktree clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| G1 a failed write exits 3 and leaves the doc (G1a-d: exit 1, swallowed, exit 0, read failure exit 1) | 4 | 4 | 0 |
| G2 rewrite changes only the last cell (G2a-d) | 4 | 4 | 0 |
| G3 unparseable-source fallback skips comment lines and uses a word boundary (G3a-d) | 4 | 2 | 2 (G3c, G3d) |
| G4 a source path must sit under `src/` (G4a-d) | 4 | 2 | 2 (G4b, G4d) |
| C-1173 delegation CLI route table equals field-core's (D1-D6: drop either route, add GET introspect, widen revoke, change method, change suffix) | 6 | 6 | 0 |
Totals counted from the table: 4+4+4+4+6 = 22 rows; killed 4+4+2+2+6 = 18; survived 4.

## Survivors (each ran the whole file; none killed)
- F-M21-1 LOW (G3c): the fallback skips only comments that start in column 0 (`not ln.startswith("#")`) with no test failing; an indented comment would be counted as a read.
- F-M21-2 LOW (G3d): dropping the word boundary in the fallback passes; `FIELD_X_Y` would match `FIELD_X`.
- F-M21-3 LOW (G4b): `"/src/" in p and p.endswith(rel)` passes; a path ending with a partial segment would match. Near-equivalent for real paths.
- F-M21-4 LOW (G4d): the backslash normalisation of the anchor path is unpinned (Windows only).
New PR only.

## Not done
Whole `tools/tests` not run. The G-mutants were applied to `tools/environment_anchors.py` on main as it is now (C-1191 later added a CI step; the tool itself is unchanged since 27bc1218 per the commit message, which I did not verify with git log).
