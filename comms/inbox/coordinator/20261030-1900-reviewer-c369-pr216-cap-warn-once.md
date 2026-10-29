# C-369 reviewer report (Lane 5): PR 216 fix/spend-governor-cap-warn-once-c364 @388bc6c (C-364; my C-359 F-C359-1)

VERDICT: PASS on the exact head 388bc6c (base 250bda8; clean on current main 241a941, i.e. with the merged PR 214). The legacy-cap warning now comes once per stored row and process, carries no value, the `/health` gauge still counts every row on every call, the clamp behaves exactly as before, and my mutants (log per read, never log, key by value, key by agent only) all die. One LOW note on the shape of the once-state (unbounded by design, not atomic). Class and file:line only; no values beyond the repository's constants.

OBJECTIONS FIRST
1. F-C369-1 LOW: the once-state is a module-level set with no lock and no size limit (core.py:90, `_cap_row_warned`; the check and the add at :450-452 are two steps). Concurrency: I read one legacy row from 32 threads released together, 4000 times, with the thread switch interval at one microsecond: 0 trials produced more than one line (worst case 1 line in 128,000 reads). The window exists in principle (a duplicate line would be harmless), I could not make it happen. Memory: one tuple per distinct `(agent, three stored limits)` ever read through the legacy branch; it grows by one for each distinct stored value of a legacy row (200 direct rewrites of one row: 200 keys) and never shrinks. The API cannot write a value above the bound (422), so the set only grows from direct database writes or from rows that already existed; agent churn through the API does not leak. The PR 213 policy path (`_policy_row_warned`) has the same shape. [HIGH, run]
2. The key holds the raw stored limits (`limits[k]` before the clamp, core.py:450) in process memory; they are never logged (my "log carries the key" mutant dies). A heap dump would show them; not a log leak. LOW. [HIGH, read and run]
3. One commit on 250bda8; author and committer Don Hagell noreply; core.py (10 lines changed), tests/test_legacy_cap_rows_c316.py (+64). [HIGH]

ASSUMPTIONS
1. Own worktrees on the GX10: the head and a copy for the mutants; a store copy with the legacy row written by hand. [HIGH]

REASONING
1. Card item (1), once per row: the state is keyed by `(agent_id, limit_cents, token_limit, action_limit)` as stored (field names and values only inside the key, the message names the agent and the field names); a row rewritten with another value warns again (test), a change in any one of the three columns warns again (test), each legacy agent warns once (test, three agents). Probe on the head (the C-359 probe: a status, three spends, a caps read and rewrites): one warning line where the PR 208 head produced five. [HIGH, run]
2. Card item (2), the gauge: `count_caps_over_bound` is unchanged and unconditional; the test `test_the_gauge_keeps_counting_while_the_warning_is_silent` reads `/health` three times between reads and sees 1 each time; in my probe it returns to 0 after the cap is rewritten at the bound. [HIGH, run]
3. Card item (3), the clamp is unchanged: the diff touches only the warning block; the clamp lines and the served value are as in PR 208. C-359 probe results on this head: stored 5*10**12 served 10**12; spending 10**12 cents answers BLOCK and one more cent BLOCK; the stored limit is untouched; a `PUT` above the bound is 422; a `PUT` at the bound stores it and the gauge goes to 0. The spend-governor suite on the head: 168 passed. [HIGH, run]
4. Card item (4), threads: objection 1. [HIGH, run]
5. Card item (5), mutants (27: 10 hand; the new tests as the judge; bytecode caching off): killed 23 of 27, including all ten hand mutants: the check removed (log per read), the log never emitted, the key built from values only (agent dropped), the key from the agent only (rewrites silent), the key ignoring the `token_limit` column, a variant that clears the memory, the set never added to (log per read), the key printed in the message, the clamp turned into `None`, and the gauge's query turned AND. The 4 survivors are generated mutants on constants and comment-adjacent lines. [HIGH, run]
6. Merge: `git merge-tree` of the head onto current main (241a941, PR 214 included): clean, no conflict in core.py (the PR touches lines 87-92 and 446-454 only). [HIGH, run]
7. Public-repo hygiene: names and constants only. [HIGH]

CONCLUSION
PASS on 388bc6c; C-359 F-C359-1 closed. Optional LOW card (coordinator numbers it): P1 builder, spend-governor core.py: wrap the check-and-add of both once-sets (cap and policy) in one lock and cap the set size (for example drop the oldest key past a few thousand entries), and say in a comment that the key holds values in memory; done when a size-limit test passes. Nothing blocks.

What I did NOT do: run the full verify or CI (the coordinator's); look at the real store.
