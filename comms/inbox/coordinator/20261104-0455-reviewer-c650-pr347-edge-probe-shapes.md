VERDICT: PASS WITH CONDITIONS on 3c2d51c29f20146f4958d5dcff9875642e5ae094 (UNVERIFIED: cloud reviewer, no GX10, no real proxy, CI not read)

Head matches the card. One commit on main 5808a5c; author and committer are "Don Hagell <13129187+dhagell@users.noreply.github.com>". Diff: 2 files, +25 -5.

OBJECTIONS FIRST
1. The 15 shapes only mean something if the real edge refuses each. I cannot start the proxy here, so whether every shape gets the edge's own 403 is unverified; the PR can only turn compose-smoke red if one is not refused. If a shape is legitimately normalised by the proxy to a refused route and answers differently, the CI job fails for a correct estate. Unknown.
2. The test rebuilds the expected list with the same string operations as the checker (tools/tests/test_kr_edge_block_r2.py:202-214 mirrors check_edge_block.py:40-54). A wrong shape written identically in both passes both. The test proves the checker sends what the test author wrote, not that each shape is a distinct attack.
3. The class is not closed: no variant puts a doubled slash or dot segment before the service prefix (e.g. a leading double slash), none uses lower-case percent-encoding of a slash, double encoding (%252e, %252F), a backslash, a trailing dot, or an encoded first letter of the other segments.
4. The count is an arithmetic pin (8 prefixes x 2 routes x 21, test_kr_edge_block_r2.py:245) plus the set equality; a variant that duplicates another would still pass if the arithmetic were updated to match. Checked: no duplicates exist today.

ASSUMPTIONS
A1 "15 extra shapes" = the 15 entries added after the original five (check_edge_block.py:46-53). A2 No real proxy or credential used; checker run only as a module. A3 Dependency-free tests selected with -k ci_checker; the other 8 tests need the field_core package (not installed here: ModuleNotFoundError) and were not run.

REASONING
1. Computed _variants for every prefix (8) and route (2): each returns 20 strings, all distinct, none equal to the base path. So 15 new shapes are distinct from each other and from the original five. HIGH.
2. Each shape is asserted: the test builds the want-set of (url, method, spoof) and compares it with the calls actually made (test:243-247); a missing or altered shape fails. Mutants on the checker (restored, worktree removed, nothing committed): remove the encoded-letter shape -> 4 failed; dot segment changed -> 2 failed; NUL shape changed -> 2 failed; weaken the refusal rule to status only -> 1 failed. HIGH for the checker-side behaviour.
3. The problem-count parameters (16 / 336 / 336) were updated to 8*2*21; arithmetic: 8*2*21 = 336. HIGH.
4. Credential/address check: the secret is read from the environment, sent only as a header, never printed (check_edge_block.py:57-72); the new lines print only path, status and the first 80 body characters. The spoofed forwarded-for value is the loopback literal. No estate address, flag value, build SHA, deploy status or credential in the diff. HIGH.
5. The mutated files were restored (git status clean in the scratch worktree).

CONCLUSION
PASS WITH CONDITIONS. Conditions:
- C1 (blocks nothing; CI/real-proxy dependent): a green compose-smoke on this head is the only evidence that the proxy refuses all 15 shapes. Coordinator to read that run by id before treating the edge as covered.
- C2 (non-blocking): F-C650-1 and F-C650-2 below.
- C3 (non-blocking): README/docstring at check_edge_block.py:3-14 still lists "case and percent-encoding variants"; update to the new shape list.

FINDINGS
F-C650-1 LOW-MEDIUM, integration/demo/fixtures/kr-edge/check_edge_block.py:40-54, class not closed: no shapes ahead of the prefix, double encoding, lower-case %2f, backslash, trailing dot. MEDIUM confidence that these matter (depends on the proxy); not probed.
F-C650-2 LOW, tools/tests/test_kr_edge_block_r2.py:202-214 expected list duplicates the implementation (objection 2); suggest literal expected strings for one prefix.
F-C650-3 LOW, check_edge_block.py:3-14 docstring stale (C3).

NOT VERIFIED: that the proxy actually refuses each shape; CI results; GX10 full suite; the 8 tests needing field_core; one interpreter version only.
