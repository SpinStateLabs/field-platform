VERDICT PASS on 896345e8105b12cdb2e4c03eecc3b3650342a68c (PR 411, Q-31, Lane 15 reviewer; delta on my own C-1052 findings F-1 and F-5 and its survivors; the author was a different lane; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. This PR answers findings I wrote (C-1052). I did not accept the builder's table; each claim was re-run with my own probe and mutants.
2. Catching RecursionError is a blunt tool: it reports "nested too deeply" for any recursion failure inside json.loads, including one caused by a nearly exhausted stack in the caller. The message is still honest, and the exit is 1, but it cannot tell the two causes apart.
3. The fix covers `parse_pack_json` only; the later canonical re-encode inside verify_pack is a second recursion site that this PR does not wrap (probe below shows it does not escape today).
4. F-2 (422 echoes the caller's raw value), F-3 (ISO week and basic date forms narrow an until) and F-4 (Unicode whitespace, one trailing NUL) are not in this PR; they are Don's rulings per the card and stay open.
ASSUMPTIONS: head current (git ls-remote = full sha above); the diff is one source file (signing.py, +8 -4) and the new test file (119 lines); window.py unchanged (the builder pins existing behaviour).

REASONING
1. Baselines: new test file 34 passed; whole attestation-reporter suite 169 passed (HIGH, run).
2. Depth sweep through the real CLI (`attest verify`, typer runner): 3 shapes (nested arrays, nested objects, alternating) x 2 placements (inside a pack-shaped signed object with a well-formed fake signature so the canonical re-encode is reached, and as the whole document) x 183 depths (1 to 59, 60 to 1300 step 7, 1500, 2000, 5000, 20000, 100000) = 1452 invocations: all exit 1 with FAILED, no uncaught exception at any depth (HIGH). On main (without the fix) the same sweep was not run; the builder's tests fail there by their own account (7 of the new tests), not re-run here.
3. F-5 (a key that is not a str): None, an int, bytes and a list give "supplied public key is not usable" (new tests; mutant below).
4. Mutants on signing.py and window.py, each judged by the new test file and, separately, by the rest of the service's suite (the pre-PR tests): 14 applied. Killed by the new file and NOT by the pre-PR suite: `except RecursionError` removed; the same with a different exception class; `AttributeError` dropped; `signed is not True` weakened to `not raw.get("signed")`; the signature-or-fingerprint guard removed; the guard checking the signature only; window whitespace strip removed (line 80); lower-case "z" dropped from the UTC test (8, all closed by the new tests). Killed by the pre-PR suite already (new tests not needed): signer guard, canonical-base64 check, BoardPack validation, window strip at line 58. SURVIVED both: `validate=True` to `False` in b64decode (equivalent: the canonical re-encode compare right after it catches every spelling, as the builder says and my C-1052 probe showed) and `TypeError` dropped from the key check's except tuple (not reached by any key I could build: str-less keys raise AttributeError, bad PEM raises ValueError; likely dead) (HIGH, run). Files restored (diff clean).
5. merge-tree: PR 411 clean against main and with PRs 317, 325, 348, 356, 369, 375, 383, 394, 402, 410; PRs 317 and 383 also merge with each other (the builder did not check the three together; I checked pairwise with 411 only).

FINDINGS
- F-Q31-1 INFO: the `TypeError` entry in the key check's except tuple is unreached (survivor); harmless, but a reader may think a TypeError path exists.
- F-Q31-2 INFO: objection 2, the RecursionError message cannot distinguish a deep document from a deep caller stack; no practical effect found.
- Carried (not in this PR): F-2, F-3, F-4 of C-1052, rulings for Don.

NOT VERIFIED: CI, GX10, a three-way merge of 317, 383 and 411, the pre-fix behaviour on main (the builder's red-first claim).

CONCLUSION: PASS. F-1 and F-5 are closed in code and by tests; the six survivors I named are each pinned by a test that dies under its mutant; no uncaught exception in 1452 depth-sweep invocations.
