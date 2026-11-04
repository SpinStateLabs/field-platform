# Lane O reviewer: PR 489 (scout P-1, lifecycle-manager sweep skips unreadable timestamps) @53c30a02f0caea0fa2ef529c35717fa73bfdc5e9. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 53c30a02. One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH). Lane B (lifecycle). I did not write the head.

Objections first: (1) fail-open: a record with an unreadable timestamp now drops out of the expiring and re-attestation findings and writes NO escalation; it appears only in the report list. A stale or expiring authority with a corrupted date is hidden from the escalation path. The builder flagged "skip and name" vs "fail the sweep" for Don: that ruling is open. (2) record_id is caller data echoed into markdown: probe with agent id "a`<newline>## FORGED HEADING<newline>- agent `ok`" renders a forged heading and bullet in the report (run, HIGH). Parity, not a regression: agent_id is echoed raw in older sections (engine.py:1210, 1218, 1226), so MEDIUM-LOW. (3) the sweep still has other unguarded parses: engine.py:540 _parse_ts(str(latest.get("ts"))) in the witness check (inside a path I did not trace for a guard; I do not know).

Run here (cloud; relative PYTHONPATH of every service src and packages src, ':' separator on Linux): lifecycle-manager suite 279 passed, matches the builder; PR test file passes.

Mutants (31, scratch worktree on the exact head; each run against the PR test file, survivors re-run against the whole service suite; a second full run gave the same table and no syntax-broken "kills"):
| Behaviour | Mutants | Killed by PR file | Killed by older tests | Survived |
|---|---|---|---|---|
| B1 bad token expires_at skipped, named, neighbour kept | 5 | 4 | 0 | 1 |
| B2 bad agent created_at skipped and named | 5 | 4 | 0 | 1 |
| B3 field names attested_at or created_at (basis) | 4 | 4 | 0 | 0 |
| B4 missing key is named, not a crash | 4 | 2 | 0 | 2 |
| B5 bad value never echoed | 4 | 3 | 0 | 1 |
| B6 clean data empty list, old report validates | 4 | 3 | 0 | 1 |
| B7 markdown section only when non-empty, names record | 5 | 4 | 0 | 1 |
| Total (counted from the rows) | 31 | 24 | 0 | 7 |

Survivors (7): 2 equivalent (token continue replaced by expires=datetime.max: still outside the horizon and still named; `raw or ""` before parse: same ValueError path); 1 non-informative mutant of mine (echo-in-md appended the config, not the value; the real echo mutants were killed); 4 real LOW pin gaps:
- F-O489-2 LOW: no test for an AGENT with a missing created_at or agent_id key (mutants reverting `.get` to `[]` survive; probe shows it is named today, not a crash). The token test exists, the agent twin does not.
- F-O489-3 LOW: the old-report test deletes the key but never asserts the default is empty (mutant default = one fake entry survives).
- F-O489-4 LOW: the markdown heading count is unpinned (mutant "(0)" survives).
- F-O489-5 INFO: B4 and B6 each have one equivalent survivor, so their real gap count is 1 of 4.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 Don's ruling on skip-and-name vs fail (objection 1), recorded before merge; if "skip and name" stands, the report should say a skipped record wrote no escalation. C3 F-O489-1 (markdown echo of record_id): strip backticks and newlines from record_id in the new section, or name it out of scope as parity in the PR text.
Optional, NEW PR only after the head is frozen: F-O489-2/3/4 pins; check engine.py:540.

Tokens/cost line: not available to me. I do not know.
