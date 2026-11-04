# Review PR524 head d299153550f10c166083140850a5e4f0e5b3de31 (reviewer wf-reviewer-A)
VERDICT: PASS WITH CONDITIONS (head d299153). Source fix correct; one changed branch has no effective pin.
ASSUMPTIONS: 1 head verified with gh = d299153 (HIGH). 2 builder note in comms is a report, not a verdict. 3 PYTHONPATH on the Linux GX10 needs ':' not ';' (the brief's ';' made the import fall back to a wrong path; I used ':' and checked engine.__file__ and hasattr _seg True).
REASONING:
1 engine.py lines 82, 84, 108 now wrap agent_id in _seg (HIGH, diff). Other _base URLs (/spend, /usage, /introspect, governed.py /check) carry ids in JSON bodies, not paths (HIGH, grep).
2 _seg = quote(safe="") plus %2E for pure-dot segments; slugs with . _ - ~ unchanged (HIGH).
3 Tests: sentinel full suite 286 passed; new file 23 passed (HIGH).
MUTANTS (engine.py mutated, tests/test_spend_client_url_quote_sc2.py run, reverted each):
| id | mutation | result |
| M1 | line 82 status (no action) unquoted | killed (6 red) |
| M2 | line 84 status (with action=) unquoted | SURVIVED (23 pass) |
| M3 | line 108 totals unquoted | killed (3 red) |
| M4 | quote safe="/" | killed (3 red) |
| M5 | quote safe="?#" | killed (2 red) |
| M6 | dot-segment encoding removed | killed (4 red) |
| M7 | .lower() on encoded id | killed (1 red) |
| M8 | "-" replaced by "_" | killed (2 red) |
| M9 | single "." left unencoded | killed (4 red) |
Counted from table: 9 mutants, 8 killed, 1 survived.
M2 proof: with line 84 unquoted, status("a/../../caps/victim", action="deploy") reaches the wire as /caps/victim?action=deploy (reproduced, HIGH). The only test of that branch, test_status_with_an_action_keeps_only_its_own_query, uses "a?x=1", which still yields one path segment because params replaces the query, so it cannot detect the regression.
CONDITION (MEDIUM): extend the action= test to parametrize over TRICKY (assert raw_path starts /status/ with count("/")==2 and params == {"action":"deploy"}); the judge gate calls without action, but other callers use the action branch.
LOW: (a) field-core clients.py same unquoted pattern, declared out of scope by builder (agree: separate card). (b) Exploitability unproven per builder; I did not test registry lookup (I do not know). (c) _seg duplicates ops-console's helper by design; a shared helper in field-core would remove drift (LOW).
CONCLUSION: PASS WITH CONDITIONS on d299153550f10c166083140850a5e4f0e5b3de31: one test addition, no source change.
