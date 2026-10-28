# C-97: C-91 finished: #25 reviewed, #26 and #30 tests at their merge commits plus mutants (teammate-don-reviewer, 2026-10-29) - PASS (FORCE format)

## Objections first
1. [LOW] #26 and #30 are mostly YAML/Caddyfile/shell; the "mutants" are text edits of the changed lines, not AST mutants, and each is tied to a check I expect the tests to make; a mutant I did not think of can still survive.
2. [LOW] Their tests are static (they read the files; no container started): "the compose file says OFF" is not "the running estate is OFF" (the C-92 checklist item B2).

## ASSUMPTIONS
- The merge commits d853ef0 (#26) and 204039e (#30) are the reviewed content (HIGH). Run on the GX10 in a fresh checkout at each sha (HIGH).

## REASONING AND RESULTS
1. #25 (brand): reviewed in 20261028-2359-reviewer-c91-pr25-and-r05-console.md (PASS with a LOW CI-regex gap). The `target="_blank"` without `rel` check you asked for: the only `target="_blank"` in console.html is line 1294 and carries `rel="noopener"` (HIGH, grep over the whole file).
2. #26 at d853ef0: tests (test_operator_auth_blank_env.py 65 lines, tools/tests/test_operator_plumbing.py 180) 44 passed. 5 text mutants, ALL KILLED: REQUIRE default `:-1` in the compose anchor (4 red); REGISTRY default a path (4 red); entrypoint.sh REQUIRE default 1 (1 red); entrypoint.sh REGISTRY default set (1 red); one service loses the operators mount (1 red). So "the flags default blank = OFF on compose and on Fly" and "every operator-block service mounts the operators file" are pinned.
3. #30 at 204039e: test_gb10_caddy_tls.py 38 passed. 5 text mutants, ALL KILLED: `tls internal` removed (4 red); `skip_install_trust` removed (1); `default_sni` removed (2); the TLS site's `reverse_proxy` target changed (1); the 18443 port mapping changed (6). The TLS listener, trust and SNI settings and the hop to 127.0.0.1:8080 are pinned. (The route-refusal behaviour of both listeners was probed with real Caddy in C-27/C-33.)

## CONCLUSION
PASS (HIGH for the 10 mutants and the two test runs; MEDIUM overall: static tests). C-91 is complete: #25, #26, #27, #30, #33 all reviewed. No new findings.
