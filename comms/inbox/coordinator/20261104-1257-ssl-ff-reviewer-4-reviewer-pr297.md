# Reviewer report: PR 297 @ 3bb2510d496e778c1d56d16b7fc5aa48ab8e5195 (C-44: three lessons in tasks/lessons.md)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Docs only: tasks/lessons.md +17, one commit on base 3ee2e5d2 (old). Author and committer = Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH). Light run, docs only. No estate address, flag, build id or deploy status.

## Objections first
1. `git merge-tree --write-tree origin/main pr297` reports a CONFLICT in tasks/lessons.md (HIGH, run by me): main appended 4 lines to the same file since the base. The conflict is textual (both sides append); the PR must be rebuilt on current main.
2. Lesson 2 says "the Co-Authored-By trailer is the only trace of the agent" and tells the reader to fix "both halves" of identity; it does not say which identity is the repository's (the Don Hagell noreply form, `13129187+dhagell@users.noreply.github.com`), which is what PROTOCOL.md and the identity guard ask for. A reader can satisfy the lesson with any no-reply address.
3. Lesson 1 tells the reader to compare "with `gh pr view`"; the cloud sessions have no `gh` for PR reads (they use the GitHub MCP tools), so the command is not available everywhere (LOW).
4. Lesson 3 is true but not applied in the repository: on origin/main three tests still spawn the base interpreter: tools/tests/test_estate_kill_watcher.py:34, test_job_grantors_c13.py:47 and test_renew_token.py:58 all use `getattr(sys, "_base_executable", None) or sys.executable`. The PR does not claim to fix them, but the lesson names the failure mode they carry (MEDIUM-LOW follow-up for a builder card).

## Verified (run by me)
- Lesson 3: in a venv here `sys.executable` is the venv's python and `sys._base_executable` is `/usr/local/bin/python3.13`, the system interpreter (HIGH).
- Lesson 1: a squash-merged branch's commits are not ancestors of main, so `git branch --no-merged` lists it (general git behaviour, HIGH).
- The citations "(ci/topology-lint, C-9)", "(D-9)", "(C-19, C-30)" refer to internal cards and branches; I did not verify them (not in the files I read; "I do not know").
- Nothing reads tasks/lessons.md (grep of *.py and .github on this head finds no reference), so no test or CI step can fail on it.

## Mutants
Docs-only prose, no test reads the file: a mutant of any sentence survives by construction. I ran none and count 0 of 0; I mark this explicitly rather than inventing a table.

## Findings
- F-C44-1 PROCESS (blocking merge as-is): conflict in tasks/lessons.md (objection 1); rebuild on current main.
- F-C44-2 LOW: lesson 2 should name the repository identity; lesson 1 should not rely on `gh`.
- F-C44-3 MEDIUM-LOW: three tests still carry the base-interpreter pattern lesson 3 warns about (objection 4); propose a builder card.

## Verdict: PASS WITH CONDITIONS on 3bb2510d496e778c1d56d16b7fc5aa48ab8e5195
Conditions: rebuild on current main with the lessons.md conflict resolved (append-only); F-C44-2 fixed in the rebuild or ruled a follow-up; CI green and a GX10 light run "docs only" on the rebuilt head. Not run by me: CI, GX10, the rebuilt head.
