# C-390 reviewer report (Lane 5): PR 237 fix/spend-governor-warn-once-docs-c384 @ba4d51f (C-384; my C-380 F-C380-1/-2)

VERDICT: PASS on the exact head ba4d51f (one commit on cd5a9a8, which is current main; author and committer Don Hagell noreply; core.py +6 -1, two test files +32). Both findings are closed and the policy-key mutant that survived at C-380 now goes red. Spend-governor suite: 240 passed on the head, 236 on the base (+4 new tests). One LOW point. Class and file:line only.

OBJECTIONS FIRST
1. F-C390-1 LOW (PROVEN): the docstring's factual aside "which the API cannot create (a limit above the bound is a 422)" is not pinned by any test in this PR; my mutant that changes the words to "is allowed" survives. The claim is true as far as I checked (SpendCapConfig limits carry `le=MAX_AMOUNT` at core.py:167-169; the rate window `le=MAX_RATE_PERIOD_SECONDS` at usage.py; the older C-246 tests pin 422 one above the bound on `/spend`), but I did not probe the policy `token_rate_limit` field over HTTP: that part is MEDIUM. [HIGH on the survivor, MEDIUM on the policy field]
2. The docstring pin is a substring test (`"larger than ``limit``"` and `"EVERY read warn again"`): it keeps the sentence present, not true. The behaviour is pinned separately by the two rotation tests, so the combination is adequate. LOW. [HIGH, read]
3. The 12-rows-through-8 and 8-rows-through-8 tests do not pin the eviction boundary (`>=` made `>` survives them) but older tests of C-373 kill it (my mutant dies in the suite). Not a gap. [HIGH, run]

ASSUMPTIONS
1. Own GX10 worktrees (head and base cd5a9a8), the spend-governor suite with the usual PYTHONPATH from its own directory; mutants by my runner (17 hand, the three warn-once and legacy-row test files as judge, bytecode caching off). [HIGH]

REASONING
1. Docstring: the new text (core.py:63-68) states that the guarantee is once per row only while the rows fit in the memory, that a larger working set read in rotation makes EVERY read warn again, gives the 12-through-8 example (48 reads), the default 1024 and the API bound, and that the `/health` gauges count every such row regardless (that last point I verified at C-380: the gauges are row counts independent of the memory). [HIGH, read]
2. Pins: `test_a_working_set_larger_than_the_bound_read_in_rotation_warns_on_every_read` (12 rows, limit 8, 4 rounds: 48 firsts), its twin for a set that fits (8 firsts), and `test_the_docstring_states_the_limit_of_the_guarantee`. Mutant dropping the limit sentence from the docstring: killed. [HIGH, run]
3. F-C380-2: `test_two_agents_with_identical_legacy_policy_rows_each_warn_once` (two agents, equal legacy rows, three reads each: exactly two log lines, one naming each agent). The mutant that removes the agent from the policy key (the C-380 survivor) is killed; so is the cap-key twin. [HIGH, run]
4. Mutants (17 hand): killed 16, survived 1 (finding 1). The earlier hand set (lock no-op, no eviction, newest evicted, bound off by one, always first, never first, key never remembered, eviction raises, default bound 1, cap key without agent, warnings carrying values, cap bypass) all die. [HIGH, run]
5. No existing assertion changed (diff: two appended tests and the docstring). Public-repo hygiene: names and constants only. [HIGH, read]

CONCLUSION
PASS on ba4d51f; C-380 F-C380-1 and F-C380-2 closed. Optional card (coordinator numbers it): P1 builder LOW, tests: pin the "limit above the bound is 422" aside for the cap and for the policy token limit, or drop the parenthesis from the docstring.

What I did NOT do: run the full verify or CI (the coordinator's); other Python versions or Windows (a comment-and-test change in one class).
