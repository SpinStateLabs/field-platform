# C-633 cloud read of PR 325 at head 34e7554 (Lane 9, UNVERIFIED: grep and read only, no test run)

VERDICT: PASS. None of the five removed names has a reader anywhere in the tree at this head; the removal is behaviour-neutral. One informational line about card text.

OBJECTIONS FIRST
1. "No reader" by grep misses a name read through a string (getattr, a config key, `__all__`, a re-export from another module, a test patching `module.Name`). I searched for those shapes (below).
2. Removing lines shifts every later line number in the file; a doc or test that pins `file:line` would break. I searched for pins on the four files.
3. An unused import can be a deliberate re-export (`from x import Y  # noqa`); none of the three carries such a comment in the diff.

CHECKS (whole tree at the head, `.git` excluded; HIGH, run)
1. `MAX_OPERATOR_LEN`, `MAX_KEY_LEN` (operator_auth.py, was :84-85): whole-word grep over code, tests, docs, tools, comms: no hit at this head. Quoted-string forms ("MAX_OPERATOR_LEN", "MAX_KEY_LEN"): none. The two regexes that hold the same numbers (`_OPERATOR_RE` 1..64, `_KEY_RE` 1..256, :84-85 after the removal) are unchanged, so the limits still apply; they just no longer have a named twin that could drift.
2. `import re` in field-core validation.py (was :18): no `re.` and no `\bre\b` in the file after removal. Its `from field_core.manifest import ...` neighbour is untouched.
3. `AgentMap` in claude-approver core.py (import line :50): no other whole-word use in core.py; no `from claude_approver.core import ... AgentMap` or `core.AgentMap` anywhere.
4. `AgentNotRegisteredError` in compliance-crosswalk api.py (:206, a function-local import in `collect_evidence`): no other use in that file; no test or module imports it from `compliance_crosswalk.api`. The name still lives in `field_core.clients` for the callers that need it.
5. `__all__`: none of the four files defines one, so nothing re-exports by list.
6. Line pins: docs/ENVIRONMENT.md cites operator_auth.py:70 and :71 (ENV_REGISTRY, ENV_REQUIRE), both above the removal, and still point at those names at this head (checked: `ENV_REGISTRY` at :70, `ENV_REQUIRE` at :71). No pin on validation.py, claude-approver core.py or compliance-crosswalk api.py found in docs, tools or the service READMEs. tools/tests/test_environment_doc.py is the test that reads those pins; I did not run it.

FINDINGS
- F-C633-1 INFORMATIONAL: card C-457 (still OPEN) cites `operator_auth.py:519` and `:548` for the two deprecated helpers. After PR 325 merges those lines are :517 and :546 (two lines removed above them). Re-read the lines, not the numbers, when C-457 is taken.
- No defect found; no card filed.

NOT VERIFIED: the test run (field-core, claude-approver, compliance-crosswalk suites, test_environment_doc.py); merge against current main.
CONCLUSION: PASS: merge after the coordinator's GX10 run.
