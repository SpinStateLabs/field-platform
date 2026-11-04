# Lane O reviewer: PR 528 (scout P-24, compliance-crosswalk tests: POST /crosswalk/markdown and run --markdown) @1ef80ddaac67d51982225e292ce0d811616ee1ab. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 1ef80dda. Lane B (crosswalk). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); one new test file (+102), no source change. I did not write the head. Claimed through dispatch.sh (R-PR528-1ef80dd).

Objections first: (1) tests-only PRs on code that already works prove the current wiring, not a requirement: where the PR says "failure statuses" it pins today's behaviour (a structurally invalid manifest is a 200 with "Manifest valid: NO"), which is a design choice nobody has ruled on (read, HIGH). (2) the file imports `test_crosswalk.resolved_manifest` as a sibling module; that works when the tests directory is on sys.path (the service's own runs, and mine with the tests directory added), and fails when pytest is run from the repo root without it; the PR text says other suites do the same (read; I did not run from the root, MEDIUM). (3) the route's `sources` field and the CLI `--agent-id` path have no test (survivors below).

Run here (cloud, scratch worktree on 1ef80dda, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 14 passed; whole compliance-crosswalk suite 383 passed, 5 skipped. NOT run: the 16-suite set, CI.

Mutants (25 written; 2 excluded, one did not apply and one was invalid (an undefined name in my mutant); 23 run in a scratch worktree on 1ef80dda against api.py, cli.py and engine.py; each against the new file, survivors against the whole service suite):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 the route answers 200 text/plain (2 valid mutants of 4 written) | 2 | 2 | 0 |
| B2 the route renders the evaluated report with agent_id and sources | 4 | 3 | 1 |
| B3 an invalid manifest is a 200 with "Manifest valid: NO" | 4 | 4 | 0 |
| B4 report text: title, citation status, coverage line | 4 | 4 | 0 |
| B5 the CLI --markdown writes the same text and says where | 4 | 4 | 0 |
| B6 the CLI without --markdown prints the JSON; exit code; --agent-id | 5 | 2 | 3 |
| Total (counted from the rows) | 23 | 19 | 4 |
B1 has 2 runnable mutants (under the 4 asked).

Survivors (4), all real pin gaps, none equivalent:
- F-O-pr528-1 LOW-MEDIUM: the route ignoring the caller's `sources` (the evidence block) survives: no test posts `sources` to /crosswalk/markdown (api.py crosswalk_markdown).
- F-O-pr528-2 MEDIUM-LOW (2 mutants): the CLI exit code for an invalid manifest is unpinned: removing `raise typer.Exit(code=1)` and changing it to 2 both survive; no CLI test runs an invalid manifest (cli.py run, "if not report.manifest_valid").
- F-O-pr528-3 LOW: `--agent-id` evidence collection (`sources = collect_evidence(agent_id)`) is unpinned: replacing it with None survives.

CONDITIONS (blocking): C1 CI green on the exact head; a tests-only PR may take a light GX10 run that says "tests only" (I could not run it).
Optional, NEW PR only after the head is frozen: F-O-pr528-1..3 pins (an invalid-manifest CLI run asserting exit code 1 first); settle objection 2 by running the file from the repo root.

Tokens/cost line: not available to me. I do not know.
