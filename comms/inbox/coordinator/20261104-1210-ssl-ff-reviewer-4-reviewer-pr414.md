# Reviewer report: PR 414 @ 2e066b77e63181b5700f39d3f8c56a1935c298f1 (B-11 vulture dead-code gate)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base acaf5f24 (old); 6 commits; files: tools/vulture_gate.py (+110), tools/tests/test_vulture_gate_b11.py (+279), .github/workflows/ci.yml (+8/-1), integration/ci-constraints.txt (+1, vulture==2.16). Author and committer of all 6 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No estate address, flag, build id or deploy status.

## Objections first (and one blocking finding)
1. BLOCKING on current main (HIGH, run by me): I merged origin/main 97dcfec1 with this head in a scratch commit (`merge-tree` clean) and ran `python tools/vulture_gate.py`: FAILED with 3 items, "stale allowlist entry (no matching finding)" for `msg` in canary.py, field_client.py and alerts.py. Cause: vulture matches names tree-wide (the gate's own docstring says so) and main now uses a variable `msg` elsewhere (packages/field-core/src/field_core/http_errors.py line 98, from the 422 handler), so the three `redirect_request(..., msg, ...)` parameters are no longer reported and their entries are stale. On the merged tree test_shipped_tree_is_clean and test_the_script_exit_code_is_the_gate_result fail (2 failed, 22 passed); CI would be red. The head alone is clean (gate exit 0; 24 passed).
2. The by-name design means the allowlist can rot again whenever any file anywhere starts using `msg`, `newurl`, `signum`, `frame` or `attrs`; each such change fails CI until an unrelated person edits the allowlist. That is the intended "stale entry fails" behaviour, but it makes the gate order-sensitive against every other PR.
3. At 80% confidence the gate finds only unused imports, unused arguments and unreachable code, and only for names used nowhere else; its value is narrow. The texts state this correctly (verified by the PR's own claim test).

## Verified
- Head baseline: tools/tests/test_vulture_gate_b11.py 24 passed with vulture 2.16 installed (relative PYTHONPATH). The CI step runs after "Install platform", installs vulture through ci-constraints (pinned ==), and the tests pin ordering, pin form and non-advisory wiring.

## Mutants (mine, independent of the PR's own 11 gate mutants and 4 wiring mutants; scratch worktree on the head; baseline 24 passed)
| # | Mutant | Result | Killed |
|---|---|---|---|
| G1 | MIN_CONFIDENCE 80 -> 95 | 4 failed | yes |
| G2 | services trees not scanned | 3 failed | yes |
| G3 | syntax-error exit (rc 1) accepted | 2 failed | yes |
| G4 | report drops the line number | 1 failed | yes |
| G5 | clean message prints "0 entries allowed" | 24 passed | NO |
| G6 | allowlist match by name only (path ignored) | 2 failed | yes |
| G7 | allowlist entry `signum` removed | 3 failed | yes |
| G10 | ci.yml: vulture dropped from the pip line | 1 failed | yes |
| G11 | ci.yml: gate step `|| true` | 5 failed | yes |
| G12 | constraints pin relaxed to >= | 1 failed | yes |
| G13 | constraints pin removed | 1 failed | yes |
| G14 | main() returns 0 on findings | 3 failed | yes |
Totals counted from the table: 12 mutants, 11 killed, 1 survived (G5). Excluded by my script (pattern not built): G8, G9. G5 survivor: no other file in the head names the printed text (grep of the head found only tools/vulture_gate.py itself), so it survives the suite; cosmetic.

## Findings
- F-B11-1 HIGH (blocks merge as-is): the three `msg` allowlist entries are stale on current main; remove them (ALLOWLIST becomes 6; test_every_allowlist_entry_names_an_existing_file asserts `len == 9`, so it must change to 6) and re-run on the rebased head. Any further allowlist entry may rot the same way before merge; re-run the gate on the exact merge candidate.
- F-B11-2 LOW: G5, the clean-line count is not asserted.
- F-B11-3 LOW (design): objection 2.

## Verdict: BLOCK on 2e066b77e63181b5700f39d3f8c56a1935c298f1 for merge; PASS on the head's own content
Reason: the gate fails on current main. A rebuilt head with the three entries removed and the count test updated needs a fresh review of the changed lines; I have not seen it. Not run by me: CI, GX10.
