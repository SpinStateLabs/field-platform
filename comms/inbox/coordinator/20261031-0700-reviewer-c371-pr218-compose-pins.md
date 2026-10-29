# C-371 reviewer report (Lane 5): PR 218 test/compose-pins-roots-c361 @cc64161 (C-361; my C-360 F-C360-1..3)

VERDICT: PASS on the exact head cc64161 (one commit on 241a941f, author and committer Don Hagell; tests only, 2 files, +76 -1). All five card items hold; one LOW test-quality finding and one LOW gap. Class and file:line only.

OBJECTIONS FIRST
1. F-C371-1 LOW (PROVEN): `test_the_real_gb10_file_with_the_proxy_service_reset_is_caught` (test_compose_static_pins.py, after the `_normal_root` tests) passes for the wrong reason. Its mutated file renames the proxy body to `proxy_unused_marker`, and `check_compose` then fails with `proxy_unused_marker: no no-new-privileges`, an unrelated check; `pytest.raises(AssertionError)` has no `match=`. It does not prove the reset removed the proxy or made the READ_ONLY_EXEMPT entry stale, and it would go red with the reset branch deleted. (The reset branch itself is pinned by `test_a_service_level_reset_removes_the_service`: my three mutants of it die.) [HIGH, run]
2. F-C371-2 LOW (PROVEN): FORBIDDEN_BIND_SOURCES was widened beyond the card to `/etc /proc /sys /var/lib/docker /var/run`; only `/`, `/etc`, `/proc` are pinned. Removing `/sys`, `/var/lib/docker` or `/var/run` from the set survives every test. `/run` (the real target of `/var/run`) and `/dev` are not in the set. [HIGH, run]
3. Sources with variables (`${X}:/h`) or `~` are not resolved; a root bind via an environment variable is invisible to this check. Not new; undocumented. LOW. [MEDIUM, read]
4. Tests only: no production code touched, so a pass proves the guards, not the compose files beyond what the current files contain (the real files pass the new list). [HIGH]

ASSUMPTIONS
1. Own GX10 worktrees (head cc64161 and base 241a941f), venv with pytest; mutants by my runner with the two test files as judge, bytecode caching off. [HIGH]

REASONING
1. Item 5, counts and assertions: the two files give 58 passed on the base and 78 passed on the head (+20, all new cases); no assertion was removed. The only changed assertion is `source != "/"` to `_normal_root(source) not in FORBIDDEN_BIND_SOURCES`, strictly stronger; the other edits are additions (the `_Reset` branch in `_services`, new PAIR_MUTANTS, the C-332 ps-only test). Nothing the C-360 PASS relied on is weakened. [HIGH, run and diff]
2. Item 1: sources are normalised by `_normal_root` before the comparison (a hand-written normaliser, not `posixpath.normpath` as the card suggested; behaviour equals the card's need: `//`, `/./`, `/.`, `/..`, `/a/..` all map to `/`, parametrised test). PAIR_MUTANTS adds `//:/h` and `/./:/h`; mutants: no normalisation, dot part kept, empty part kept, `..` not popped, `..` kept as a name, non-absolute no longer passed through: all 6 killed. [HIGH, run]
3. Item 2: long-syntax root bind (`{type: bind, source: /, target: /h}`, and the `//` spelling) is in PAIR_MUTANTS; mutants removing the long-syntax branch (source from `str(vol)` only) and the short-syntax branch: both killed. [HIGH, run]
4. Item 3: `PS_ONLY_LOG_DOCKER` pinned by a new test with a `match="the fake docker was not used"`; mutants making the assertion not require the config call, or not require `ps -a`: both killed. [HIGH, run]
5. Item 4: a service-level `!reset null` drops the service; `test_a_service_level_reset_removes_the_service` asserts the result is `{"b"}`; mutants: branch removed, old service kept, pop skipped: all 3 killed (see finding 1 for the second reset test). [HIGH, run]
6. Mutants (19 hand; two test files as judge): killed 16. Survived: set drops `/sys`, `/var/lib/docker`, `/var/run` (finding 2). Forbidden set drops `/`, `/etc`, `/proc`: killed. [HIGH, run]

CONCLUSION
PASS on cc64161; C-360 F-C360-1..3 closed. Proposed cards (coordinator numbers them): P1 builder LOW, test_compose_static_pins.py: give the proxy-reset test a `match=` (or assert the exemption-staleness message) so it fails for the stated reason; P2 builder LOW: one PAIR_MUTANT each for `/sys`, `/var/lib/docker`, `/var/run`, and decide whether `/run` and `/dev` belong in the set; P3 builder LOW: state in the docstring that variable-valued sources are not resolved.

What I did NOT do: run the full verify or CI (the coordinator's); mutate on Windows; run the whole tools suite (only the two named files).
