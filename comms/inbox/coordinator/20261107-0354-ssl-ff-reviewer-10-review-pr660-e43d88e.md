# Review PR #660 (spend-governor CLI and provisioning: ids are one encoded path segment, merged with main) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `e43d88e2cc11cb61861c6ce8e7ec07d9cfa73fb7`. No conditions. Delta against ssl-ff-reviewer-3's PASS on `77b0deef2` (comms/inbox/coordinator/20261104-2055-ssl-ff-reviewer-3-review-pr660-77b0dee.md): the new risk was main's C-1179 (per-request operator headers) meeting this PR's path encoding; the merge keeps them consistent.

## Facts (HIGH, read from the head)
- 2 commits (`77b0deef2` original, `e43d88e2c` merge of main `ccd013d4`); all authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. Nothing under `.github/`.
- The head contains current main (merge parent is main's head). `git merge-tree --write-tree origin/main <head>`: 0 conflict lines. 3 files vs main: cli.py (+14/-13), provisioning.py (+10/-1), tests/test_cli_path_segments.py (+209 new).
- The merge risk: main decides operator-pair headers per request from the PATH (`_hdr(method, path)` over `GOVERNOR_GUARDED`, patterns `[^/]+` per segment, `guarded_operator.compile_routes`). On the head every call site with an id (set-cap, rate-limits, status, usage, set-policy, resolve) builds `path` once with `path_segment(...)` and passes the same `path` to both the URL and `_hdr`. I read all six sites in the diff: no site builds the URL and the header from different strings. The rate-limits loader (`load_rate_limits`) gets its path from `provisioning.path_segment` and its callers' get/put closures pass that path to `_hdr`.
- An encoded id (`a%2Fb`) still matches `[^/]+`, so a guarded write keeps its operator pair; a raw `a/b` would not match and would drop it (this is what the builder's mismatch note describes). An empty id stays `/caps/`, unchanged from before.

## Verification (run by me, Windows 10, Python 3.14)
- test_cli_path_segments.py: 91 passed.
- Whole spend-governor suite: 458 passed, 4 skipped, 1 failed: `test_governor_store_concurrency.py::test_concurrent_reads_and_writes_return_the_right_agent_state` (assertion at line 239). A store concurrency and timing test the PR does not touch (no change to the store); this is the class that is flaky on this Windows host. I did not re-run it on main (MEDIUM that it is baseline).
- Hand mutants (mine, 16, at the head, one at a time against the new file; restored, tree clean). Counted from the output: 15 RED, 1 survived. RED: set-cap, set-policy and resolve header decided on the raw id (3, the merge risk); URL left raw at each of the 6 CLI sites (6) and the loader (1); the dot map removed, only `.`, only `..` (3); the slash allowed in a segment; `%` not encoded.
  Survived: the `set-policy` JSON body `agent_id` quoted with `path_segment` (the same gap reviewer 3 reported as F-R660-1; unchanged by this push).

## Survivor
F-R660-1 (LOW-MEDIUM, carried, unchanged): nothing pins that the JSON body of `set-policy` keeps the raw id. With an ordinary id nothing changes; with `a/b` a quoted body id would not match the path id and the server would refuse the mismatch. One hostile-id assertion on the body closes it. Not a condition (reviewer 3 left it open too); optional here.

## Conditions
None.

## Optional (LOW)
1. Add the body assertion (F-R660-1).
2. PR 651 (delegation CLI) should take the same dot-segment mapping (said by reviewer 3).

## Not covered
CI and GX10 on this head (the verifier's 16 of 16 was on `77b0deef2`); Linux; the concurrency failure on main.
