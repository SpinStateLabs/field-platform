# Review PR #716 (conformance-sentinel: escalation-trigger edges pinned, SPEC rule stated, S6-14) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `390a4cf5ace9c78bbf54025107441eb141ea8742`. This head is the follow-up to reviewer-3's PASS WITH CONDITIONS on `8697ab0c` (comms/inbox/coordinator/20261105-0933-ssl-ff-reviewer-3-review-pr716-8697ab0.md); its one MEDIUM condition is checked below.

## Facts (HIGH, read from the head)
- 2 commits (8697ab0c, 390a4cf5); 2 files: services/conformance-sentinel/SPEC.md (+6), tests/test_escalation_trigger_edges.py (new, 109 lines). No source change: engine.py step 7 (`t, a = trigger.lower(), req.action.lower()`, `if t in a or a in t`) is untouched. Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The delta since reviewer-3's head is three tests in tests/test_escalation_trigger_edges.py (+30).

## Reviewer-3's condition (M5, M8: SPEC says "case-insensitive substring in BOTH directions", nothing pinned the case)
Closed, with the test shape reviewer-3 asked for: an upper-case trigger against a lower-case action; a lower-case trigger against an upper-case action (the action `Draft Invoices` is put into both the manifest scope and the token scope because scope is an exact match, which the comment states); and the reverse leg (an action inside a longer trigger) with upper case.

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_escalation_trigger_edges.py: 8 passed on the head (96 s; the stack fixture is slow here). The builder's note says its own whole-file run was cut by a timeout and left to CI; I ran the whole file and it passes.
- Mutants (mine, 9 hand mutants on engine.py step 7, one at a time against this file; file restored from backup, tree clean afterwards). Counted from the output: 9 RED, 0 survived: trigger not lowercased (M5); action not lowercased (M8); neither lowercased; forward leg only; reverse leg only; trigger stripped; `and` instead of `or`; skip only the empty trigger; skip empty and whitespace-only triggers.
- The SPEC sentences added (a match in both directions, case-insensitive; only the empty string and a single space match every multi-word action) are each pinned by one of these mutants.

## Conditions
None.

## Not covered
The whole conformance-sentinel suite (reviewer-3 ran 268 passed on the old head; the delta is tests only); Linux; did not rebase on current main (stale base ebb027a2, clean per reviewer-3).
