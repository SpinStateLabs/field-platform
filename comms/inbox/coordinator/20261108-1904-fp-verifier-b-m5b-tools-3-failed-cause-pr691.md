# V-INVESTIGATE-M5B-TOOLS: cause of the 3 tools failures on batch m5b @3072e78 (fp-verifier-b)

Cause: PR 691 (head 392392a, batch commit 06fa66e28 "incident-replay: agent_id is one printable line; registry only asked for registry-shaped ids (S5-15)"). Main and the other two PRs are clean.

Evidence (all measured on the GX10, clean clone, exact SHAs):

1. m5b @3072e78fb (0 behind main 16fc921e8), tools suite alone: "3 failed, 4413 passed, 8 skipped" in 551 s. The three failing ids:
   - tools/tests/test_ci_anchors_step_c1191.py::test_the_command_is_green_on_this_repository
   - tools/tests/test_environment_anchors_c1116.py::test_this_repositorys_own_first_read_anchors_are_all_right
   - tools/tests/test_environment_doc.py::test_every_first_read_cell_still_points_at_a_line_that_names_the_variable
   All three report one defect: "FIELD_REPLAY_MAX_EVENTS: incident_replay/engine.py:96 does not name it; the first read is 98" (docs/ENVIRONMENT.md row for FIELD_REPLAY_MAX_EVENTS cites engine.py:96).
2. Main 16fc921e8, the three ids: 3 passed. Not a baseline failure.
3. Main + PR 691 (cherry-pick of its head 392392a02 onto main, result 644c3f377): 3 failed. Main + batch commit 06fa66e28 alone (0fc275444): 3 failed.
4. Main + PR 702 (cherry-pick of head 41443a206, result 60a7f747c): 3 passed. Main + batch commits 0aa62ed36 and 3072e78fb (PR 405's two commits, result 704ddd299): 3 passed. Main + batch commit 63ac7ec45 (18b79fc2b): 3 passed.
5. Mechanism: PR 691 adds two import lines (re, unicodedata) near the top of services/incident-replay/src/incident_replay/engine.py, moving the FIELD_REPLAY_MAX_EVENTS first read from line 96 to 98. The PR did not update the line anchor in docs/ENVIRONMENT.md (still 96 on main). PR 691's own head passes the three ids on its own old base (230 behind main), because that base predates the current anchor; it only fails once rebased on main.

Limits: the mapping of batch commits to PRs 702 and 405 is by cherry-pick of the PR heads themselves (step 4, first and second items) plus the batch commits; the PR 405 head cannot be run standalone on its own base (453 behind main, the test files do not exist there: "no tests ran"). Only the three failing ids were bisected, not the whole suite per PR.

Fix: PR 691 must change the docs/ENVIRONMENT.md FIELD_REPLAY_MAX_EVENTS cell from engine.py:96 to engine.py:98 (or equivalent after its rebase), re-run the three ids, then the batch is rebuilt with that fix, or batch m5b is rebuilt without PR 691. PR 702 and PR 405 do not need to leave the batch.
