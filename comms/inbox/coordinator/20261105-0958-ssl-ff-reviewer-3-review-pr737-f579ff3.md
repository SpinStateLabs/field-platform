# Review PR 737 @ f579ff3d3227aa3c1a498fddffe679dc650f9e55 — lifecycle-manager render_markdown sections + one-line registry text (S7-12)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM)** on head f579ff3d.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: engine.py +23/-10 (new `_inline`, applied at 20 call sites in `render_markdown`), one new test file (7 tests).

## Mutants. Baselines unmutated: new file 7 passed; whole lifecycle-manager suite 276 passed.
Call-site rows drop `_inline` on one source line (`_inline(` -> `str(`); function rows mutate `_inline`.
| # | Mutant | Result |
|---|---|---|
| L1191 | expiring agent_id | SURVIVED |
| L1192 | expiring granted_by + scope | SURVIVED |
| L1198 | re-attestation attested_by | SURVIVED |
| L1199 | re-attestation agent_id + owner | KILLED |
| L1200 | re-attestation basis | SURVIVED |
| L1207 | orphans agent_id, status, reason | KILLED |
| L1220 | retention offending (agent_id, retention_days) | SURVIVED |
| L1222 | retention unresolvable (agent_id, manifest_ref, reason) | SURVIVED |
| L1226 | retention detail | SURVIVED |
| L1235 | witness detail | SURVIVED |
| F1 | drop category Cc | SURVIVED |
| F2 | drop category Cf | SURVIVED |
| F5 | drop whitespace collapse | SURVIVED |
| F6a | drop marker `#` | KILLED |
| F6b | drop marker `-` | KILLED |
| F6c | drop marker backtick | SURVIVED |
| F6d | drop marker `*` | SURVIVED |
| F6e | drop marker `>` | SURVIVED |
| F6f | drop marker `+` | SURVIVED |
| F7 | no escape | KILLED |
| F8 | escape with wrong char | KILLED |

Equivalent, not counted: F3 (drop Zl) and F4 (drop Zp). `str.split()` already splits on U+2028 and U+2029, so category handling for them is redundant (general knowledge, HIGH).
Totals counted from the table: 21 valid rows, 6 killed, 15 survivors. 0 anchor failures.
Every survivor was run against the whole suite (276 baseline): 276 passed each time, so none is caught elsewhere.

## Findings
1. MEDIUM: the PR claims registry-derived text stays on one line. Only orphans and re-attestation agent_id/owner are pinned. The retention section (offending, unresolvable, detail), the witness detail, expiring (agent_id, granted_by, scope) and attested_by/basis are sanitised in code but no test would notice if the sanitisation were removed. 8 of 10 call-site rows survive. Add one injection case per section.
2. LOW: control and format characters other than newline (F1 for NUL/ESC, F2 for U+200B/U+202E) and the whitespace collapse (F5) have no test; the one injection test uses `\n`, which `split()` handles anyway.
3. LOW: markers `` ` ``, `*`, `>`, `+` are in the escape list but unpinned (4 survivors).
4. Observation: every `_inline` value is interpolated mid-line after a `- ` prefix, so the leading-marker escape never prevents a forged block element on its own; the newline collapse is the real defence. The docstring over-states the escape; harmless, outputs `\#`. `e.token_id[:8]` in the expiring line is not passed through `_inline` (token ids are minted ids, not free text; MEDIUM confidence).
