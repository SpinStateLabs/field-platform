# Q-82 read of PR 436, head 492a8bf0f4ce8e68ec5de809de810e1c66140fdf (git ls-remote refs/pull/436/head agrees)

Reader: grooming assistant, not the author (Lane 12 per its report 20261102-0700-builder-lane12-c1117-pr436.md). READ, NOT MEASURED: nothing was run. I read the patches of boundary_echo_allowlist.txt and test_boundary_echo_lint_c505.py and listed the test names in test_boundary_echo_blindspots_c1117.py (I did not read its bodies).

Findings
1. HIGH: the lint source IS in this PR, because the lint lives inside tools/tests/test_boundary_echo_lint_c505.py (+29 -7). My Q-82 question "was the lint changed elsewhere" is answered: no, it is changed here. The card said "tests only"; it is tests only in the sense that the lint is a test file, but it widens what the repository's lint test fails on.
2. HIGH: the lint gains four things, all read from the patch: `secho` as a cli sink; `sys.stdout.write` and `sys.stderr.write` as cli sinks; `logging.getLogger(..).<log method>` as a log sink; and a new `visit_Return` that records a `reply-field` finding for a returned dict literal holding tainted text under a detail, error, message, reason, note or msg key. Each matches a blind spot Lane 17 measured, and the module docstring is updated to say so.
3. HIGH, for the coordinator: the allowlist gains THREE entries, each `allow | DEBT`, found by the new rules in existing code: compliance-crosswalk regwatch.py `_observe` (reply-field), force-gateway api.py `_authorize` (reply-field), lifecycle-manager api.py `scheduled_tick` (reply-field). Each reason says the text of a failure reaches an API caller. So three real echoes are recorded as allowed debt, not fixed. Not hidden (they are tagged DEBT with a reason), but a decision for you: allow them, or open cards to fix them as C-1114 does for the 422 handler. I print no values here.
4. MEDIUM (read, not run): the new return rule walks every dict inside the returned expression, so a dict nested in a call is included. That can flag more than a bare `return {...}`. I do not know whether the corpus tests cover that.
5. Not checked (I do not know): the blindspots test bodies, that each new rule fails without the lint change, the floors test (`test_floors_are_the_numbers_the_lint_names`) counts, and the CI result.

Result: no defect found in what I read. This is not a PASS. Point 3 is the item that needs a decision.
