VERDICT: PASS on c8cedb010abfea607644ffe4be1e6c06c8752e29  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). This PR fixes F2 of my own red-team card R-RT-HARD-4; I did not write it. The finding is closed on the measured behaviour; the standing gate stays open.

R-PR862-c8cedb0, PR 862 (agent-registry: the manifest_ref 422 returns a fixed body). Applies to this head only. gh pr view and the fetched pull/862/head both give c8cedb01; one commit on main 41afda50 (0 behind); `git merge-tree` clean. Files: api.py +5/-4, cli.py +1/-2, one existing test file +2/-2, a new test file +97. Nothing under .github/.

OBJECTIONS FIRST
1. The only way to show F2 is closed is to re-run the reproduction, not to read the diff. I re-ran my F2 probe on this head (in-process, FIELD_MANIFEST_DIR set to a made-up path, POST /agents with an unresolvable manifest_ref): short "nope.yaml", a key-shaped string, a 100000-character ref, "../../etc/passwd", a UNC-style path and a NUL-bearing string all answered 422 with the SAME 209-byte body (`error`, `reason`, a fixed `hint`): no echo of the ref (echo_ref False on all six), no directory (dir_leak False on all six). Before the fix the 100000-character ref produced a 100,258-byte body and the made-up directory appeared in every body. HIGH (measured).
2. The armed-mode PATCH path is covered only through the shared helper `unresolvable_manifest_ref` (the PR says so); the new test checks the helper returns the same fixed shape and that POST is fixed, not an armed PATCH request. Both routes call the one helper (api.py), so a divergence is not possible without editing it; I did not send an armed PATCH. LOW.
3. With the operator mode OFF a PATCH carrying an unresolvable ref is accepted (200) and the 200 returns the stored record including the ref: that is the documented OFF behaviour (PR 707's README row), the caller's own data in a 2xx, not the 422 this fix concerns. Not a defect. HIGH.
4. The operator-terminal command `registry add` still prints the reason and the variable NAME but no longer the directory value; the builder removed the value rather than add a boundary-echo allowlist entry (I re-ran the lint: 61 passed). An operator now has to look up the directory themselves. LOW (usability).
5. A grep of services/*/src for other 4xx bodies that carry a manifest directory found none (ops-console's "FIELD_MANIFEST_DIR is not configured" names the variable, not a path). HIGH on the grep, not exhaustive for every service message.

ASSUMPTIONS
A1 F2's severity (MEDIUM) stands as I rated it; this PR removes both parts (the unbounded echo and the path). A2 The 209-byte fixed body is the right design: it keeps `reason` (missing or invalid) from a closed set.

REASONING / CHECKS
1. Diff read in full: `unresolvable_manifest_ref` returns {"error": "manifest_ref does not resolve", "reason": <missing|invalid>, "hint": <fixed text naming the registry's manifest directory without its value>}; the `manifest_ref` and `manifest_dir` keys are gone; cli.py prints the reason and the variable name. Two older D3b tests that asserted the echo now assert its absence. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): test_manifest_ref_422_no_echo_rt4 + test_d3b_manifest_ref_resolves 26 passed, 0 failed; tools test_boundary_echo_lint_c505 61 passed; `environment_anchors.py --check` 0 wrong anchor rows. I did not re-run the whole agent-registry suite (about 17 minutes on this box); the PR touches the one helper and the CLI line. HIGH on the counts.
4. Mutants on a copy of the head, the new test file (and for E6 also the older D3b file), -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| E1 | the body echoes the caller's ref | KILLED |
| E2 | the body carries manifest_dir | KILLED |
| E3 | the hint carries the directory value | KILLED |
| E4 | an extra key in the body | KILLED |
| E5 | `reason` carries the first 20 characters of the ref | KILLED |
| E6 | the refusal is None when the reason is "invalid" | KILLED (by the older D3b file; SURVIVES the new file alone) |
| E7 | the CLI prints the directory value | KILLED |
| E8 | the CLI drops the variable name | KILLED |

Counted from the table: 8 run, 8 KILLED (E6 only with the older file), 0 SURVIVED, 0 NOT APPLIED. HIGH.

CONDITIONS
C1 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this PASS the head is frozen.
C2 (optional, new PR) one armed-mode PATCH request test through the HTTP route (the helper is covered, the route is not); a case with an "invalid" (present but unparseable) manifest in the new file.

NOT VERIFIED
GX10 / Linux, CI, the whole agent-registry suite on this head, an armed-mode PATCH request.

CONCLUSION
F2 is closed: the 422 is a fixed 209-byte body for every ref I tried, with no caller text and no directory, the CLI keeps the operator informed without the path, 8 of 8 mutants die, 26 tests and the boundary-echo lint pass, identity is correct. PASS on c8cedb01; the GX10 and CI gate remains the coordinator's.
