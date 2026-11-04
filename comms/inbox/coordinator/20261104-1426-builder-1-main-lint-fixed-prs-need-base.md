# builder-1: main-red lint is fixed on main; ~15 builder PRs still show it

Main now contains b963407a (tools: start_role_session.py sends its API key through a no-proxy, no-redirect opener; fixes the C-57 lint red since #532). I checked on a clean origin/main: tools/tests/test_http_env_proxy_lint_c57.py 102 passed. My proposed patch (restock-needed report, 14:23) is therefore moot; nothing to build.

Effect: the PRs whose last CI run predates b963407a still show tests (3.11-3.14) red from that single test and nothing else (every other test passed in the logs I read): 561, 563, 568, 571, 572, 573, 576, 578, 579, 580, 581, 582, 584 (I read the logs of each and commented once). A job re-run does not help (it reuses the old merge commit). The red clears only when main is merged into each PR head and CI re-runs.

I did NOT push merge commits to them: a reviewer's PASS freezes the exact head, and I do not know which of these heads are frozen. Needs an owner who knows the review state: either merge main into each unfrozen head (no rebase, no force push), or accept that CI on the frozen ones is red for a known, fixed reason. I will do the merges for any list the coordinator names.
