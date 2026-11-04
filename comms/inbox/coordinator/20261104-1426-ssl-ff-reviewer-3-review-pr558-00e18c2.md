# Review PR 558 @ 00e18c239225b99c3b80535b5c5404ad8e6deac5 (force-gateway: count and log dropped ledger appends and spend forwards) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 00e18c23. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. Replacing `except Exception: pass` with logging in a request path can change behaviour: a re-raise, a log line that carries a URL or value, or a counter on the wrong field. Probed (L4-L7, P3-P4, L3, P2).
2. Two new `/health` fields change a public shape; the PR has `test_health_keeps_its_existing_fields`. A consumer that rejects unknown keys would break: I did not check consumers (ops-console reads `/health`; not read).
3. The docs rows in `docs/ENVIRONMENT.md` re-anchor 5 lines of `api.py` (+6): a stale anchor is a CI failure now (C-1191 step). Checked below.

## Facts (HIGH)
- Head fetched via refs/pull/558/head = 00e18c23; 1 commit; base origin/main 97dcfec1 (main has since moved one unrelated commit; `git merge-tree` with current main is clean); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 4 files, +144 -10: `api.py` (two counters, two warnings, two `/health` fields), `docs/ENVIRONMENT.md` (5 anchors +6), `services/force-gateway/README.md`, `tests/test_ledger_spend_drops_counted_c9c.py` (+122, 7 tests).
- `python tools/environment_anchors.py --check` on the head: "0 wrong anchor row(s)", exit 0.
- Baseline unmutated: force-gateway suite 455 passed (relative `PYTHONPATH` incl. sibling service `src`).

## Mutants (the new file first; a survivor then ran the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| ledger drop counted once, on its own counter, never re-raised, logged by type only, payload not logged (L1-L7) | 7 | 7 | 0 |
| spend drop counted on its own counter, logged by type only, logged (P1, P2, P3, P5) | 4 | 4 | 0 |
| spend drop never re-raised (P4) | 1 | 0 (killed by the whole suite) | 1 |
| `/health` has both fields, correct values, start at 0 (H1-H5) | 5 | 5 | 0 |
Totals counted from the table: 7+4+1+5 = 17 rows; killed in the new file 16; P4 survived the new file and was killed by another test in the whole suite (so 17 of 17 are killed by the suite).

## Findings
- F-R558-1 LOW: the new file does not pin that a failed spend forward does not re-raise (P4); another file does. Cosmetic coverage gap.
- F-R558-2 LOW: counters are plain ints on `app.state`, incremented from a request path; under threaded workers a lost update is possible. Not tested; the counters are advisory ("never affecting the request").

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
