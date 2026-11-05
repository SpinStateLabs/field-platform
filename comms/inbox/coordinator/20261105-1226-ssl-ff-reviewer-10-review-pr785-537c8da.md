# Review PR #785 (force-gateway: pin telemetry.analyze, document bold confidence tag, S8-28) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `537c8da4c5caad2b4646af50a0468bc06ac0728f` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 2 files: services/force-gateway/tests/test_telemetry_analyze.py (+156), README.md (3 lines). telemetry.py untouched. Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- README claim checked: the protocol file is `services/force-gateway/src/force_gateway/data/protocol.md` and its [E] section prescribes `**HIGH**` / `**MEDIUM**` / `**LOW**` (bold); `_CONFIDENCE` counts bold and bracket forms, upper case only (no `(?i)`) (HIGH). The README path `data/protocol.md` is package-relative, which is accurate.
- The three regex findings re-derived from telemetry.py: `that (is|'s) incorrect` needs a space before `'s` so "that's incorrect" does not count; `i'd be happy to` consumes `happy to` (one hit); `\bobjection` matches "objections" (prefix). All pinned as current behaviour, not fixed (author leaves finding 1 to Don).
- tests/test_telemetry_analyze.py: 88 passed on the head. Full force-gateway suite (PR: 536) not run by me.

## Mutants (telemetry.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | bold alternative dropped | RED |
| M2 | bracket alternative dropped | RED |
| M3 | confidence made case-insensitive | RED |
| M4 | MEDIUM dropped from bold form | RED |
| M5 | "this is not accurate" dropped | RED |
| M6 | "premise is false" dropped | RED |
| M7 | "hope this helps" dropped | RED |
| M8 | "certainly!" to "certainly" | RED |
| M9 | `^` dropped from the REASONING marker | SURVIVED |
| M10 | `re.M` dropped from ASSUMPTIONS | RED |
| M11 | CONCLUSION check dropped | RED |
| M12 | "would break" dropped | RED |
| M13 | "failure mode" dropped | RED |
| M14 | "general knowledge" dropped | RED |
| M15 | "i don't know" dropped | RED |
| M16 | clean_of_flattery forced True | RED |
| M17 | has_confidence_tags forced True | RED |
| M18 | apostrophe-s regex "fixed" | RED |
| M19 | METHOD_LABEL text changed | SURVIVED |
Totals counted from the table: 19 mutants, 17 RED, 2 SURVIVED.

## LOWs (optional, new PR)
1. M9: a mid-line "REASONING:" still yields cot_structure True; add a case where only REASONING is mid-line (the existing mid-line case evidently exercises a different marker).
2. M19: the label is compared to the module constant, not its text, so a changed label passes; pin the literal if the dashboard shows it.
3. Decision (author's): fix `that's incorrect` (raises the corrections count for existing traffic).
