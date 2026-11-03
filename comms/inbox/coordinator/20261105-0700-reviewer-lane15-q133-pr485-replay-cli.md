# reviewer Lane 15: Q-133, PR 485 (C-1204, incident-replay replay CLI tests), head 1325e8832db8ad98d45dd34ec05ed59605dfdd92

VERDICT: PASS on 1325e8832db8ad98d45dd34ec05ed59605dfdd92, low risk, with three LOW pin gaps (F-Q133-1 to F-Q133-3). Head re-read with git ls-remote refs/pull/485/head at claim time and again before this note, unmoved. 1 commit on main cd3b7690 (contains main), author and committer Don Hagell noreply. One file added, `services/incident-replay/tests/test_cli_c1204.py`, +143/-0, no source change (git diff --stat). Not Lane 11. Local Windows run, relative PYTHONPATH (";" separated), no stdin, scratch worktree, read-only on the PR. Not a GX10 run, GitHub CI not read. No estate value in this note.

## OBJECTIONS FIRST (limits)
1. The file starts with `pytest.importorskip("typer")`: where `typer` is absent the whole file is skipped and reports green. `typer` is a declared dependency of the service (`pyproject.toml`) and `ci.yml` line 47 says it comes in with field-core, so I expect no skip in CI, but that is read from the comment, not from a CI run (MEDIUM). Here `typer` is installed and the run showed 11 passed, 0 skipped.
2. 29 hand mutants on a 60-line module are a floor, not a proof.
3. `httpx.post` is replaced by a recorder, so the tests show what the CLI sends, not what the service answers.

## THE QUESTIONS (from the card)
1. MADE-UP DATA, NO NETWORK, NO REAL FILE. HIGH. The secret is the literal `made-up-shared-secret-0123456789`, set through `monkeypatch.setenv` and never printed by the tests. The agent id, the URLs (`replay.invalid`, `127.0.0.x`) and the timestamps are made up. `httpx.post` is replaced for the length of each test; uvicorn is replaced by a fake module in `sys.modules`; the only file written is under `tmp_path`. A read of the file for open, socket and real hosts finds none. The operator pair is deliberately not pinned (the docstring points to C-1181).
2. THE NON-200 CASE REALLY WRITES NOTHING. HIGH. `test_a_non_200_from_replay_markdown_exits_one_and_writes_nothing` asserts exit code 1, `not target.exists()` and the error on stderr. Measured: mutant C11 (a non-200 ignored on the markdown route) is KILLED; C14m (error not on stderr) KILLED; C15m (exit code 2) KILLED.
3. MUTANTS ON incident_replay/cli.py. Baseline 11 passed. 29 mutants: 23 KILLED, 6 SURVIVED (4 distinct points; see findings).
   - KILLED (23): trailing slash kept on the base URL; default port changed; env name changed; version printed without the package name; markdown route replaced by /replay; JSON route replaced by /replay/markdown; since and until swapped; JSON timeout changed; auth headers dropped on either route; a non-200 ignored on either route; JSON route treating only 5xx as an error; error text off stderr on either route; exit code 2 on either route; the written-to message without the path; the printed body altered; the markdown branch never taken; the serve host default exposed (0.0.0.0); the serve port default changed; serve ignoring the host; serve ignoring the port; the agent id dropped from the body; serve running no app.
   - SURVIVED: C8a (markdown timeout 30 s -> 10 s); C13m (the markdown route treating only 5xx as an error); C16 (the file written without `encoding="utf-8"`); C20 (`if markdown:` -> `if markdown is not None:`).
4. NO ESTATE VALUE. HIGH. Nothing but made-up ids, `.invalid` hosts and loopback addresses; the secret is a literal and is the only thing in the file that looks like a credential.

## RESULTS
- New file: 11 passed, 0 skipped. Whole `services/incident-replay/tests`: 108 passed (170 s).
- The scratch worktree is clean after every run; each mutant was restored.

## FINDINGS
- F-Q133-1 LOW (pin gap, markdown error path): the two non-200 tests use different codes (422 on the JSON route, 500 on the markdown route), so mutant C13m (markdown route: `status_code >= 500`) passes all 11 tests: a 4xx on the markdown route would then be written to the post-mortem file and reported as success. The JSON-route twin (C13j) is killed. Pin: make the markdown test parametrized over 422 and 500, or add a 422 case.
- F-Q133-2 LOW (pin gap, markdown timeout): the JSON test asserts `kwargs["timeout"] == 30.0`; the markdown test does not, so C8a survives. Pin: add the same assertion to the markdown test.
- F-Q133-3 LOW (platform-dependent pin): the UTF-8 pin (`# utf-8, not the locale`) only bites where the locale is not UTF-8. Measured both ways: with Python's UTF-8 mode on, C16 passes all 11 tests (SURVIVED); with UTF-8 mode off on this machine (locale cp1252), C16 is KILLED (the markdown success test fails on the check mark) and the unmutated file passes 11. On a Linux runner with a UTF-8 locale C16 survives, so CI cannot show that pin. Pin: monkeypatch `Path.write_text` and assert the `encoding` argument is `"utf-8"`.
- Note (no action): C20 is equivalent, a `Path` is always truthy.

## CONCLUSION
PASS on 1325e883: a test-only file of made-up data and stubs that pins the routes, the request shape, the auth header, the exit codes, the stderr text, the serve defaults and the "writes nothing on error" claim; 23 of 29 hand mutants die, the other six being one equivalent and three LOW pin gaps (two on the markdown route, one platform-dependent). What this PASS does not cover: GitHub CI and GX10 on this exact head (none from me), whether `typer` is installed in CI (read, not run), and the service side of the calls. After this PASS builders do not push to the branch (head-freeze); the pins above can go in a follow-up PR.
