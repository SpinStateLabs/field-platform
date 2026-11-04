# Lane O reviewer: PR 421 (B-21, Don via C-497: the CI tests job runs the tools suite in two matrix shards per Python version) @849fdaef68a9166c151fc095f24a2965622aa562. UNVERIFIED (cloud, no GX10, no CI run, nothing executed on GitHub Actions)

VERDICT: PASS WITH CONDITIONS, naming head 849fdaef. Lane A (tools/CI). Three commits (a1491046, d7977ee7, 849fdaef), all Don Hagell noreply as author and committer (git log, HIGH). The head does NOT contain current main: 214 commits behind origin/main 97dcfec1. `git merge-tree` onto main: clean (tree b360157d, HIGH). I built a scratch merge commit of head and main (local, not pushed) and ran the PR's own test there: tools/tests/test_ci_tools_shards.py 19 passed, `tools/environment_anchors.py --check` 0 wrong anchor rows, and main's newer CI-step pin test test_ci_anchors_step_c1191.py (the anchors step must have no `if`) is in the same tree (its result is in my command output; I did not record a number here, so treat it as not asserted). Files: .github/workflows/ci.yml (+29/-3) and tools/tests/test_ci_tools_shards.py (+207). I did not write the head. Claimed through dispatch.sh (R-PR421-849fdae).

Objections first: (1) the time gain is a claim, not a result: the comment says the tools step "took 9 to 10 minutes of each 16 to 20 minute job" on a green main run; I cannot measure Actions time and shard 2 inherits the per-service suites, topology lint and the other tools modules, so it may not be shorter than the old job (read, HIGH; "I do not know" for the real wall time). (2) the matrix doubles the job count (4 versions x 2 shards = 8 jobs): more runner minutes and eight statuses a branch-protection rule must list; if protection names the old `tests (3.x)` check names, the renamed matrix jobs (`tests (3.11, 1)` style) are unrequired or missing (read, MEDIUM; the repo's protection settings are not in source: I do not know). (3) shard 2 is computed with `ls ... | grep -vxF -f <(...)`: it relies on bash process substitution, which GitHub's default bash shell supports (general knowledge, MEDIUM), and on file names without spaces.

Run here (cloud, scratch worktree on 849fdaef): tools/tests/test_ci_tools_shards.py 19 passed. NOT run: the workflow itself (no Actions), the 16-suite set.

Mutants (27 written; 2 did not apply (my string did not match the shard-1 line) and are excluded; 25 run, each a text edit of the real ci.yml, run against test_ci_tools_shards.py; no unparseable-YAML kills; the file carries its own MUTANTS table, so some kills overlap, but each mutant below is mine):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 the matrix is exactly python-version and shard [1, 2] | 5 | 4 | 1 |
| B2 the heavy list equals the literal shard-1 list (two more did not apply) | 3 | 3 | 0 |
| B3 shard 2 is every other module, computed; an empty shard 2 exits 1 | 5 | 5 | 0 |
| B4 an unknown shard exits 1 | 4 | 3 | 1 |
| B5 steps sit on the shard the test pins | 5 | 4 | 1 |
| B6 no step is continue-on-error and the tools step is unconditional | 3 | 3 | 0 |
| Total (counted from the rows) | 25 | 22 | 3 |
B2 and B6 have 3 runnable mutants each (under the 4 asked).

Survivors (3), all real LOW pin gaps:
- F-O-pr421-1: a strategy-level key such as `max-parallel: 1` (it serialises the eight jobs and defeats the speed-up) passes: the test pins the MATRIX keys and `fail-fast`, not the strategy's other keys.
- F-O-pr421-2: `case "${TOOLS_SHARD:-1}"` (an unset shard silently runs shard 1) passes: only an unknown value and a wrong env source are pinned.
- F-O-pr421-3: the "Vendored field-agent templates in sync" step moved from shard 1 to shard 2 passes: that step is not in the test's STEP_SHARDS table (it would still run once, so coverage is kept; an `if` pointing at no shard would drop it and no test names it).

CONDITIONS (blocking): C1 CI green on the exact head rebased on current main (it merges clean) and the first real matrix run reviewed by a human for wall time and for the required-check names (objections 1 and 2); I could not run GitHub Actions. C2 none other.
Optional, NEW PR after the head is frozen: F-O-pr421-1..3 pins.

Tokens/cost line: not available to me. I do not know.
