# builder (Lane 3): C-286 (PR 147), the C-267 CI defect, GX10 results

OWNED DEFECT: my C-267 stack put a second `env:` key in the compose-upgrade-smoke job of ci.yml; GitHub rejected the workflow. I did not read CI on the draft PR before asking for review. Fixed (one env block, FIELD_GB10_LAN_IP merged into the existing block) on ci/private-address-functional-c267-r3 @79b865a3b2438e382f03b411e63cc99ce25f8724 and on ci/private-address-functional-c267 (PR 134) @7df0938250123ddf8c39cca31bf5250bbc28a80a. PR 134 showed "no checks reported" a minute after the push; I will read its CI before any review request.

C-286, PR 147, head 2a7e0fa46e838e3a585e94f5857ad735923abbec (test/duplicate-key-lint-c286, from main fb52eef): tools/tests/test_yaml_duplicate_keys.py, 10 tests: a SafeLoader subclass refusing a repeated mapping key at any depth, run over every .github/workflows file and every integration compose file (compose tags read as plain values, the `<<` merge key not data); 2 mutants red (a second env in compose-upgrade-smoke, a repeated restart in the base compose); it flags the real defect (ci.yml from commit 6f37fa4: "duplicate key env: lines 352 and 365"). A first draft skipped tagged mappings; a test of mine caught it. PR 147 CI was pending when I looked; GX10 not yet run (load was above the limit: held).

GX10 full set results on the heads reported earlier, 16 suites and 0 failures each: c241 (PR 129 @7c189dc), c267b (PR 134 part-b head @6f37fa4, before the ci.yml fix; the fix touches only ci.yml), c151r3 (108-r3 @86e2f46), c152r3 (118-r3 @1a8b7fb). c242r3 (125-r3 @44cbec7) is running (I started it as a full run through the same chain; it had not finished).

Not started and not touched: no new full run while load is above 8.
