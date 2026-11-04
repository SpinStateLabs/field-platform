# Reviewer (lane B, ops-console): PR 523 (scout S-C3) fleet halt refuses an unreadable registry answer before halting

**Verdict: PASS WITH CONDITIONS on head `9f867f4065095a1d8ededf5f313eeb6a6436cd94`.** HIGH CARE (the halt path). Head unchanged at start and end; base is current main (contained); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `ops_console/api.py` `fleet_halt` (+9): when `domains` is not given, the registry answer must be a list of dicts whose `domain` is a str or None, else `HTTPException(502, "registry answered with a shape the console cannot read ... nothing was halted")` before any kill-switch call; new `test_fleet_halt_registry_shape_sc3.py` (13 tests).

## Objections first
1. The check is a positive whitelist (list, dicts, str or None domain) but the rest of the comprehension reads `a.get("status")` and `a.get("domain") or "general"`: a hashable-but-odd `status` is harmless, an unhashable `domain` is excluded by the check; I found no read the check misses (HIGH, read).
2. An EMPTY fleet answers 200 `all_ok: true`, `domains: []`: "nothing to halt" reads as success while an operator is trying to halt. The author left it as an open question for Don and pinned today's behaviour with a test; I agree it is Don's decision (an operator-facing safety call), not a defect of this PR.
3. The registry answers `null`, `{}` or `""`: `null` would still reach the comprehension if the check were loosened (mutants below show it is unpinned).

## Measured (GX10 ~/ff-work/wt-ln523, relative PYTHONPATH incl. sibling service src, own venv, python -B)
New file 13 passed. ops-console suite: 470 passed (127 s). CI at read: see Conditions. I did not compare the suite count with main (PR file is the only addition, +13). 16-suite not run by me.

## Mutants (22 rows; source restored, worktree clean). My Z4 anchors first failed on the em dash in the message; I re-ran Z4 with an anchor that avoids it.
| Behaviour | Killed | Survived |
|---|---|---|
| Z1 a non-list answer is a 502 | 2 | 3 (gaps: an empty dict `{}`, an empty string `""` and a `null` answer are unpinned; each reaches or can reach the halt as an empty fleet or a 500) |
| Z2 a non-object item is a 502 | 4 | 0 |
| Z3 a non-text domain is a 502 | 3 | 1 (gap: a list-valued domain; unhashable inside the `sorted({...})`) |
| Z4 the 502 is a fixed 502 and echoes nothing of the answer | 5 | 1 (neutral: adding only the TYPE NAME of the answer, not its content) |
| Z5 well-formed fleets halt the same domains (retired excluded, None is general) | 3 | 0 |
Totals counted from the table: killed 2+4+3+5+3 = 17; survived 3+0+1+1+0 = 5; 22 rows. Of the 5 survivors, 4 are real unpinned inputs and 1 is neutral. Z1 and Z3 are below the 4-kill bar.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (read as pending, see the CI line above).
- C2: GX10 16-suite 16/16 on a head containing main.
- C3 (Don, not the author): decide the empty-fleet answer (200 all_ok, a 4xx, or all_ok false); until then the test pins "as is today".

## Findings (non-blocking; new PR only)
- F-523-1 LOW-MEDIUM: add `null`, `{}`, `""` and a list-valued `domain` to the parametrised wrong-shape test (Z1, Z3).
- F-523-2 INFO: the 502 text is a fixed string; a future edit that formats the answer into it is caught by 5 of 5 echo mutants.
