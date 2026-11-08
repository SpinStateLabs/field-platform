# Review R-PR978-c5b8daa
**VERDICT: PASS** for head c5b8daa16efc5d0b0cc826dbeb3d56629f3b59c2 (S11-13, spend-governor README cites the real metering tests; pin that every cited test exists)

Reviewer: fp-reviewer-b. Independent (did not build this PR).

## Checks
| Check | Result | Confidence |
|---|---|---|
| Head equals PR head | yes | HIGH |
| Author and committer | Don Hagell 13129187+dhagell noreply, 1 commit | HIGH |
| Files | README.md (1 line), tests/test_readme_cited_tests_exist.py (+67); 0 under .github/ | HIGH |
| Secrets / estate addresses | none in added lines | HIGH |
| Behind main | 32 commits, `merge-tree` clean | HIGH |
| Stale cite `test_d1_metering` | absent from main's tests; `git log -S` finds it only in the Phase F integration commit, as the PR says | HIGH |
| Two new cites exist and match the claim | test_one_allow_meters_exactly_one_and_self_stays_zero (one ALLOW = one metered row) and test_log_only_meters_every_shadow_allow_including_steps_1_to_4 (shadow ALLOWs metered) | HIGH |
| Lints (boundary-echo, blindspots, http-env-proxy, no-line-cites, environment-doc, environment-anchors) | 299 passed | HIGH |
| New test file | 13 passed | HIGH |

## Mutants (scratch tree of all test dirs plus README/SPEC)
| # | Mutant | Result |
|---|---|---|
| S1 | restore the d1 cite | KILLED |
| S2 | sentinel cite names a missing function | KILLED |
| S3 | cite names a missing file | KILLED |
| S4 | drop both new sentinel cites | KILLED |
| S5 | log-only cite names a wrong function | KILLED |
| S6 | gateway cite function truncated | KILLED |
| S7 | bare nonexistent file token in README | KILLED |
| S8 | nonexistent file::test cite in SPEC.md | KILLED |
| S9 | `tests/` path that does not exist | KILLED |
| T1 | resolver drops service-relative path | KILLED |
| T2 | function regex matches any mention, not only `def` | SURVIVED |
| T3 | FILE_TOKEN drops the `::name` group | KILLED |
| T4 | DOCS drops README | KILLED |
| T5 | bare-name lookup drops tools/tests | SURVIVED |

Totals: applied 14, killed 12, survived 2, not applied 0. Baseline 13 passed.

## Full spend-governor suite on head
380 passed, 4 skipped, 1 failed: test_governor_store_concurrency.py::test_concurrent_reads_and_writes_return_the_right_agent_state. The same test fails on current main in isolation (343 s on main, 364 s on the head). Pre-existing, not attributable to this PR. HIGH.

## Optional LOWs (new PR, not conditions)
1. T2: no negative test shows the `def` anchor matters; a citation satisfied only by a comment or call would pass if the regex were loosened.
2. T5: no current citation resolves via tools/tests, so that directory entry is unpinned.
3. The failing concurrency test (about 6 minutes then fail, on both) deserves its own card.
