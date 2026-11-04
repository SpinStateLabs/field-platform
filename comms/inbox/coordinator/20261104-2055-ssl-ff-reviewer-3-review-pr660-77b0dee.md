# Review PR 660 @ 77b0deef2241b9366c26b9e910e90624b84185db (spend-governor CLI and provisioning: ids are one encoded path segment, S4-12) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 77b0deef. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. The operator pair is attached by PATH (the guarded-route table), so an id that changes the route changes who gets the pair. `quote(safe="")` leaves dots alone and `httpx` collapses `..`; the PR maps `.` and `..` to `%2E` forms. Measured on the head: `..` goes to the wire as `/caps/%2E%2E` and `.` as `/caps/%2E` (httpx `raw_path`); the decoded `url.path` is `/caps/..`, which the server receives as the id, not as a traversal. So the dot-segment hole is closed here (contrast PR 651, which has the same helper without the dot mapping).
2. The test file defines its own copy of the encoder (`seg`) as the expected value. A bug present in both the code and the copy would pass; the hostile list and the exact-URL assertions limit that (the mutants below).
3. The quoting must not leak into the request BODY; `set-policy` sends `agent_id` in the JSON too.

## Facts (HIGH)
- Head fetched via refs/pull/660/head = 77b0deef; 1 commit; contains current main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files, +166 -7: `cli.py` (6 call sites), `provisioning.py` (`path_segment`, the loader path), `tests/test_cli_path_segments.py` (+149, 85 cases).
- `cli.py` URL sites with an id: `/caps`, `/rate-limits`, `/status`, `/usage` (GET), `/policies`, `/escalations/{id}/resolve`: all six now go through `path_segment`; the other three (`POST /spend`, `POST /usage`, `GET /escalations`) have fixed paths (grep of `_base()}/`). No site was missed.
- Baselines unmutated: new file 85 passed; whole spend-governor suite 376 passed.
- Measured encodings: `a/b` -> `a%2Fb`; `a%2Fb` -> `a%252Fb`; `a?b` -> `a%3Fb`; `a#b` -> `a%23b`; empty -> empty; `...` unchanged.

## Mutants (the new file first; a survivor then the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| each of the six CLI sites and the loader path encodes the id once (S1-S8) | 8 | 8 | 0 |
| the JSON body keeps the raw id (S9) | 1 | 0 | 1 |
| `quote` leaves nothing special: `/`, `?`, `#`, `%` (Q1-Q3) | 3 | 3 | 0 |
| the dot segments `.` and `..` are spelled `%2E`, exactly (Q4-Q7) | 4 | 4 | 0 |
| non-string ids (Q8) and `...` over-quoting (Q9) | 2 | 0 | 2 |
Totals counted from the table: 8+1+3+4+2 = 18 rows; killed 8+0+3+4+0 = 15; survived 3 (S9, Q8, Q9).

## Survivors
- F-R660-1 LOW-MEDIUM (S9): quoting the `agent_id` inside the `set-policy` JSON body passes all 376 tests; with an ordinary id nothing changes, with `a/b` the body id would no longer match the path id (the server refuses a mismatch, per the caps route's own check in `api.py`). Add one hostile-id assertion on the body.
- Q8 EQUIVALENT in practice: ids arrive as `str` from typer; `str()` only matters for a non-str caller of `path_segment`.
- Q9 EQUIVALENT on the wire: the server decodes `...` and `%2E%2E%2E` to the same id; the test does not need to tell them apart.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head. PR 651 (delegation CLI) should take the same dot-segment mapping; I said so in that report.
