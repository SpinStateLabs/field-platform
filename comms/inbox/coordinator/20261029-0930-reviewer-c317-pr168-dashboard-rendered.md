# C-317 reviewer report (Lane 5): PR 168 ops-console tests: the dashboard escaping probe must prove something was rendered @cd594162acc5eab5a87a74221aba0a61563e2cbd (C-268, my C-256 P1/P2)

VERDICT: PASS on the exact head cd594162acc5eab5a87a74221aba0a61563e2cbd. The harness now records which of nine containers held the payload at some step; the shipped-page test asserts all nine in every payload and mode; a dead flow (an early `return` in the function that fills a container) comes back with that container missing, and all of my own vacuity variants from C-256 do the same. The mutant-case sweep stops at the first flag, so the cost rose by only a few seconds. Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. "Rendered" is judged by the text `__pwn` being present in the container. Every payload carries it and it survives `esc()` and `JSON.stringify`, so a container that shows the payload text only through a path I did not think of would count as alive; a container rendered from fixed text (not API data) would count as dead. The nine ids are fixed in a list; a tenth container added to the page is not covered until someone adds it (the test `test_every_container_is_covered_by_a_dead_flow_case` pins the two lists to each other, not to the page). LOW. [HIGH, read]
2. The dead-flow cases kill a flow by inserting `return;` at the top of nine named functions, each asserted to appear exactly once in the page; renaming a function fails the assertion (good) but a refactor that moves the fill into a helper makes the case meaningless until updated. LOW. [HIGH, read]
3. The branch is one commit on main a946d26 (main has moved); author and committer Don Hagell noreply; two files under services/ops-console/tests/. [HIGH]

ASSUMPTIONS
1. jsdom 24.1.3 and node on the GX10, as in C-256. [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr168, base a946d26): core_services 2244 passed 4 skipped; tools 2082 passed 3 skipped; agent-registry 277; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 257; lifecycle 212; attestation 66; ops-console 232 passed (222 plus the 10 new cases: nine dead-flow cases and the list check); claude-approver 162; field-agent 150; topology_lint OK; EXTRA defence-shield 166. The ops-console step took 115.6 s against 107.9 s on the PR 164 run of the same base: about 8 s more, not the 64 s the C-256 file added (the early-stop `any_hit` cancels queued probes at the first flag). VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH, run]
2. The shipped page, all 35 combinations (7 payloads times 5 modes), harness run directly: `maxhit` 0 and all nine containers rendered in every one (35 of 35). [HIGH, run]
3. My vacuity variants from C-256, run against this harness (payload 0, mode ok): the page whose renderAgents throws: `rendered` lacks agents and escalations; the overview-dead page: the same two; the drawer-detail-dead pages (m052 and the esc-free variant): `d-details` missing; the bulk-dead page (m032): `bulk-result` missing. The syntax-broken and empty pages still fail the harness (exit 1) as before. So the dead flows that passed the C-256 harness are now visible. [HIGH, run]
4. Mutants on the harness (6 hand, test file `test_dashboard_escaping.py`, bytecode caching off): the "rendered" test made always true (`includes("")`), the output list replaced by all containers, replaced by none, the container lookup skipped, one container (`platform`) dropped from the list: all 5 KILLED; the sixth, an initial value for `maxhit` of -1000, is equivalent (the running maximum is taken against non-negative counts), my mutant, not a gap. [HIGH, run]
5. The C-256 P2 trim was applied in the other direction: `any_hit` returns at the first flagged probe and cancels the rest, and the mutant cases still use payloads 0, 2, 5 in the five modes; so coverage is as before and only the time fell. [HIGH, read]
6. Public-repo hygiene: no address, flag value or secret. [HIGH]

CONCLUSION
PASS on cd59416; C-256 P1 closed, P2 satisfied differently, P3 (the comment naming the equivalent survivors) not done and still LOW. No new cards.

What I did NOT do: test in a real browser; add new payload families; check the harness against a page with a new container.
