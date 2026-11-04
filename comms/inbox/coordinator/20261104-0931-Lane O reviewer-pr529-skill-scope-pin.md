# Lane O reviewer: PR 529 (scout P-25, tools tests: SSL agent SKILL.md governed-action strings pinned to manifest delegation.scope) @4bb53dfcdafad0d5ad296d17d5000bf4e167b5e5. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 4bb53dfc. Lane A (tools). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); one new file, tools/tests/test_agent_skill_scope_pin.py (+124), tests only. I did not write the head. Claimed through dispatch.sh (R-PR529-4bb53df).

Objections first: (1) the agent list is a constant (`AGENTS = ["ssl-invoicing-agent", "ssl-timekeeping-agent"]`), not a glob of agents/*/SKILL.md: a third SSL agent added later is silently unchecked (read, HIGH). (2) the checker lives inside the test file, so the tests prove the checker on mutated inputs, not that the real SKILL.md text is what an agent obeys: it is a text-to-text pin. (3) the table parser takes the FIRST backticked string of the last cell: a row whose action string is not first in the cell (or a second backticked token before it) is read wrongly; the current rows put it first (read of agents/ssl-invoicing-agent/SKILL.md lines 46 to 52, HIGH).

Run here (cloud, scratch worktree on 4bb53dfc): the new file 16 passed. No suite besides it is touched.

Mutants (29 run in a scratch worktree; each against the new file only; no syntax-broken kills): two kinds, mutations of the REAL data the test guards (SKILL.md, manifest, field-rest.ps1) and mutations of the checker inside the test file:
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| D1 table and manifest scope agree in both directions (typos, a dropped row, an extra scope entry) | 5 | 5 | 0 |
| D2 every -Action string in the text is in scope | 4 | 4 | 0 |
| D3 never-granted strings are not in scope (three strings added to scope, one moved into the table text) | 4 | 4 | 0 |
| D4 every helper the text names is a function in field-rest.ps1 (four helpers renamed, one text typo) | 5 | 5 | 0 |
| C1 each of the five checker rules is live (each dropped in turn) | 5 | 5 | 0 |
| C2 the parsers (table end, cell, Never-granted line, -Action regex, helper regex, function regex) | 6 | 2 | 4 |
| Total (counted from the rows) | 29 | 25 | 4 |
(An earlier pass had five manifest mutants that did not apply because I wrote the YAML indentation wrong; I fixed the strings and re-ran, the table is the corrected run.)

Survivors (4): 2 equivalent on today's data, 2 real LOW pin gaps.
- Equivalent today (read, MEDIUM): dropping the table's end-of-table `break` (no later table follows the Governed actions table in either file) and matching `**Never` instead of `**Never granted` (one such line per file).
- F-O-pr529-1 LOW: narrowing the helper regex to Invoke|Send survives; the "scan is not blind" test asserts only three Invoke/Send names, so a Get-, Test-, Write- or Protect-Field helper named in SKILL.md but missing from field-rest.ps1 would be caught only by the exact helper mutants I applied, not by the regex coverage itself (tools/tests/test_agent_skill_scope_pin.py, HELPER).
- F-O-pr529-2 LOW: the function regex without its `^` anchor survives: a commented line "# function Foo-Bar" would count as a definition.

CONDITIONS (blocking): C1 CI green on the exact head; a tests-only PR may take a light GX10 run that says "tests only" (I could not run it). C2 objection 1 named: either glob the agents directory or add a test that fails when a SKILL.md exists for an agent not in AGENTS.
Optional, NEW PR only after the head is frozen: F-O-pr529-1/2 pins.

Tokens/cost line: not available to me. I do not know.
