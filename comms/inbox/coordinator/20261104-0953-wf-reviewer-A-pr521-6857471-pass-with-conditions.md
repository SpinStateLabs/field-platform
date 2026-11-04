# Review PR521 head 6857471a3d43163ec82307f4a161c6368a560fae (reviewer wf-reviewer-A)
VERDICT: PASS WITH CONDITIONS (head 6857471). Source change correct; tests pin 3 of the 11 interpolation sites the PR claims to cover.
ASSUMPTIONS: 1 head verified with gh (HIGH). 2 builder note is a report, not a verdict (no verdict on this head in comms inbox). 3 tests run on GX10 with PYTHONPATH using ':' (engine.__file__ and hasattr _md True).
REASONING:
1 engine.py render_markdown: _md applied at agent id title, integrity detail (3 places), integrity notes, agent record, authority table (token, granted_by, scope), timeline (event_type, summary), first_failure (clause_id, summary), counts key, manifest_detail, RACI role/party, accountable grant (HIGH, diff).
2 Left raw: window since/until, generated_at, ts[:19] slices, pm.method (a class-default string at engine.py:233, not payload text). Builder declares other inline markdown chars (backticks, *, brackets) unescaped: a value can still add emphasis or close a code span on its own line (HIGH, builder note and diff). Not a heading forge.
3 Python re \s already covers U+2028/2029/NEL, so the explicit class is redundant but harmless (HIGH).
4 incident-replay suite 106 passed; new file 9 passed (HIGH).
MUTANTS (engine.py mutated, tests/test_markdown_injection_sc6.py run, reverted each):
| id | mutation | result |
| M1 | regex collapses only CR/LF | killed |
| M2 | timeline summary raw | killed (4 red) |
| M3 | first_failure summary raw | killed (4 red) |
| M4 | integrity detail raw in "> " blockquote | SURVIVED |
| M5 | RACI party raw | SURVIVED |
| M6 | authority-table granted_by raw | SURVIVED |
| M7 | pipe escaping off | killed |
| M8 | cap 300 -> 3000 | killed (2 red) |
| M9 | agent_record name raw | SURVIVED |
| M10 | accountable grant granted_by raw | SURVIVED |
| M11 | integrity note raw | SURVIVED |
| M12 | timeline event_type raw | SURVIVED |
| M13 | title agent_id raw (line 512) | SURVIVED |
| M14 | .strip() removed | killed |
Counted from table: 14 mutants, 6 killed, 8 survived.
CONDITION (MEDIUM): the PR claims every ledger/grant/registry interpolation is sanitized, but 8 of 14 mutants, each reverting one real site, pass. Add a parametrized test that renders a PostMortem with "\n\n## FORGED" in every field (agent_id, ledger_integrity_detail both branches, integrity_notes, agent_record fields, authority granted_by/scope, event_type, clause_id, counts key, manifest_detail, RACI role/party, accountable_grant) and asserts no heading line "## FORGED" and no extra table-row split. Source needs no change.
LOW: (a) inline markdown chars (backticks, *, [], <) unescaped inside a value, builder-declared, outside S-C6 scope; a backtick in manifest_ref/clause_id can close its code span (MEDIUM-LOW, not run). (b) 300-char cap truncates long legitimate summaries in markdown only (JSON unchanged), intended. (c) re import placed after field_core import, cosmetic.
CONCLUSION: PASS WITH CONDITIONS on 6857471a3d43163ec82307f4a161c6368a560fae: add the per-site forge test; no source change.
