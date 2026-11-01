# BUILDER Lane 1: C-1073 closed on PR 359; C-1066 claimed; backlog lines stale

- C-1073 (PR 359): fixed before the release, by Lane 1's C-1059 follow-up: head d3e807e (test only, 4 lines in packages/field-agent/tests/test_canary_response_cap_c106.py: the fixture server now reads the request body before it answers; no assertion weakened; the cap assertion is unchanged). CI on d3e807e, run 41268375657: 7/7 success, including tests (3.14). Mechanism (HIGH on mechanism, MEDIUM on why only 3.14): the fixture answered without draining the request body, so an early close became a reset for a slow reader; reproduced at socket level, not on 3.14. Reviewer delta needed on d3e807e. Please mark C-1073 done.
- C-1066 (PRs 369, 394, 331; released because Lane 12 is down): taken by Lane 1, same branches only, one commit per finding. In work.
- BACKLOG lines that are stale (no card of mine): B-12 is covered by PR 403 (C-1044, commit 1dd2b37); B-16 is covered by PR 331 (Lane 12, C-573: parse_anchors plus the raise test and an agreement test).
- Taken from the backlog and in work: B-10 (reset hooks private), B-11 (vulture gate), B-15 (decide and is_guarded pins).
- Not run in this note: GX10.
