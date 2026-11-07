# Review R-PR858-c6c3aee: PR 858 (kill-switch: bound POST /heartbeat; B-RT4 F1), re-review after my C1 to C3
Head reviewed: c6c3aee70515843495c20a0aeaa4e4ca9562f503 (3 commits; c6c3aee7 merges main ccd013d4). `git merge-tree` against current main is clean (tree 554ddc91). Earlier report: head cd4a9e37, PASS WITH CONDITIONS (C1 rebase against S4-4, C2 refused shadow agents invisible and not told to halt, C3 registered ids over 128 characters).

## VERDICT: PASS (C1 to C3 closed; one LOW pin gap and the carried no-eviction observation)

## Checks (HIGH, run by me)
1. Identity: all 3 commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; against main 4 files (api.py +51/-?, store.py +22, a 240-line test file, one ENVIRONMENT.md row).
2. C1 closed: one `MAX_HEARTBEAT_ID_LEN` (main's, the PR's duplicate is gone, comment "defined once, above"); the check is `len(agent_id) > MAX_HEARTBEAT_ID_LEN or not _HEARTBEAT_ID_RE.fullmatch(agent_id)` with the 422 text "agent_id is not a valid agent id" replacing main's S4-4 text; the S4-4 control-character rule is subsumed (the registry pattern excludes every control character).
3. C2 closed in the way I offered: a malformed or over-long id is now counted (`heartbeat_ids_refused`, in `/health`) and logged (first and every 100th, no id); the docstring now says a shadow agent refused for the cap or a malformed id "is neither recorded nor told to halt, and is visible ONLY by the counters ... and the log line". The behaviour (no halt answer) is unchanged and now stated.
4. C3 closed by documentation and a test: the docstring says a registered agent with an id over the limit cannot check in and shows as stale, "a limit to cap in the registry (a separate card), pinned by a test" (my probe's case is in the new test file).
5. Tests on head: test_heartbeat_bounds_rt4 plus 6 neighbouring heartbeat and liveness test files 190 passed (3m33s on this host); `environment_anchors.py --check` 0 wrong rows.
6. Mutants on api.py and store.py, 22 run: 21 killed, 1 survived (counted from table). The 14 mutants K1 to K19 re-run are from my first report, now K9 and K19 are killed (they survived before).
| # | Mutant | Result |
|---|---|---|
| K1 | no length check | killed |
| K2 | length `>=` (128 refused) | killed |
| K3 | no pattern check | killed |
| K4 | pattern uses `match` | killed |
| K5 | cap not passed to the store | killed |
| K6 | known ids also blocked at the cap | killed |
| K7 | cap off by one | killed |
| K8 | registered agents counted under the cap | killed |
| K9 | count includes every row | killed (was SURVIVED) |
| K10 | cap refusal counter not incremented | killed |
| K14 | cap refusal answers 503 | killed |
| K15 | malformed id answers 400 | killed |
| K16 | store never refuses | killed |
| K19 | refused id echoed in the 429 text | killed (was SURVIVED) |
| H1 | malformed-id counter not incremented | killed |
| H2 | `heartbeat_ids_refused` removed from `/health` | killed |
| H3 | malformed-id log line never written | killed |
| H4 | malformed-id log line every time | killed |
| H5 | malformed refusals counted on the cap counter | killed |
| H6 | the malformed-id 422 text echoes the id | SURVIVED |
| H7 | id length limit 256 | killed |
| H8 | the malformed-id log line carries the id | killed |

## Observations (LOW)
- H6: no test pins that the 422 text for a malformed id never carries the id (C-1189's rule, which main's old text kept). Today the text is fixed; one assertion would pin it.
- Carried: unregistered rows are never evicted (no purge), so retired typo ids fill the 500 slots over time; a TTL for `unregistered` rows would remove the permanent saturation. The registry's missing length cap (C3) is a separate card.
- Carried: a shadow agent past the cap still gets 429 without the halt fields (now documented).

## Not verified
Whole kill-switch suite; behaviour against a real registry; GX10 16/16.

## Head frozen at c6c3aee7.
