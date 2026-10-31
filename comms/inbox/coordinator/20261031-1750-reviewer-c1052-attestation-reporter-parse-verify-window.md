VERDICT: PASS WITH CONDITIONS on main acaf5f241f00754442c7adbbb0290769dbfe52c5 (services/attestation-reporter, read-only audit, UNVERIFIED: no GX10, no CI logs)

Card C-1052, reviewer Lane 15. Scope: signing.py parse_pack_json (:245), _no_duplicate_keys (:225), _finite_float (:238), verify_pack (:253), served_signing_from_env (:153); window.py parse_period (:55), normalise_bound (:77), resolve_window (:101). Everything below was run on a scratch worktree of main (Python 3.13.17), nothing committed, every mutated file restored.

OBJECTIONS FIRST
1. The word "never" in the card question does not hold for the CLI: parse_pack_json lets RecursionError escape on deeply nested input (F-1).
2. The window parsers do refuse every malformed input I tried, but two accepted forms silently change the window instead of refusing (F-3, F-4). A board pack with a quietly narrower window is a worse failure than a 422.
3. The 422 text echoes the caller's own value, unbounded in length (F-2). Same class as the PR 366 echo.
4. The tests execute almost every line but do not pin five behaviours (mutants below). A refactor could regress them with a green suite.
5. Everything is single-version: Python 3.13.17 only. The service says >=3.11; the NUL and week-format behaviour comes from datetime.fromisoformat and may differ on 3.11 and 3.12 (not run).

ASSUMPTIONS
- "fail closed" = a 4xx / named refusal / non-zero exit, never a pass and never a 500.
- verify_pack and parse_pack_json are CLI-only: grep finds no HTTP route that calls them (cli.py:118-128 only). The HTTP surface of these symbols is the window (api.py:100) and served signing (/health).

FINDINGS
F-1 (LOW, HIGH confidence, probed). parse_pack_json (signing.py:245-250) passes input to json.loads; a plain array nested 100000 deep, or 20000 deep inside an otherwise pack-shaped object, raises RecursionError. cli.py:123 catches (OSError, UnicodeDecodeError, ValueError); RecursionError is none of them, so `attest verify` prints a traceback and exits 1 with no "FAILED -" line. Fail closed by exit code, not by named refusal. 900 and 3000 deep inside a pack are refused normally ("signature INVALID"); a balanced 5000-deep array parses. Smallest fix: catch RecursionError in parse_pack_json and raise PackVerificationError. Integers over 4300 digits raise ValueError and reach the generic "cannot read the pack" line at cli.py:123: fine.
F-2 (LOW, HIGH confidence, probed through the app on /pack and /pack.html). api.py:100 returns HTTP 422 with str(exc); window.py:69, :71-73 (period), :92 and :98 (since/until) format the caller's raw value with !r. A 3000-character period gives a 3113-byte 422; a 9000-character since gives 9059 bytes. The body is application/json even on /pack.html, so there is no HTML sink. No key path or key material is echoed. Per my PR 366 report, agent-registry and federation-broker already strip the value: a precedent exists. Needs Don's ruling (strip the value, or cap its length).
F-3 (LOW-MEDIUM, MEDIUM confidence on impact, HIGH on the calculation). normalise_bound (window.py:80-90) goes through date.fromisoformat, which on 3.11+ accepts ISO week and basic forms. "2026W44" and "20261031" are accepted. As an until, "2026W44" is the Monday of that week at 23:59:59.999999 (probe: 2026-10-26T23:59:59.999999+00:00), so a caller meaning "through week 44" gets a window about six days short, with no refusal and no note. The API help text says "ISO 8601 date or timestamp (a date alone = ...)" (api.py until_doc). Fix is either a strict YYYY-MM-DD pattern or a documented rule. Needs Don's ruling.
F-4 (LOW, HIGH confidence, benign). (a) str.strip() at window.py:58 and :80 trims Unicode whitespace: "2026-Q3" followed by U+2028 returns 200 as 2026-Q3, against the docstring "Strict: nothing else parses". (b) One trailing NUL after a seconds-precision timestamp is accepted (CPython fromisoformat quirk); two NULs, or a NUL plus text, are refused. In both cases the resulting window equals the clean input's. Not a security issue.
F-5 (LOW, HIGH confidence, API misuse only). verify_pack(raw, key) with a key that is None, an int or bytes raises AttributeError, not PackVerificationError (the except at signing.py:269 lists TypeError, ValueError, UnsupportedAlgorithm). Unreachable from the CLI (read_text gives str) and from HTTP. A public PEM with one trailing NUL still loads with the same fingerprint (tolerated, harmless).

PER-SYMBOL ANSWER (fail closed? echo?)
- parse_pack_json / _no_duplicate_keys / _finite_float / _no_constant: duplicate key at any depth (including an escaped spelling of the same key) and NaN, Infinity, -Infinity, 1e999, -1e999, 1E400 give PackVerificationError. Empty, whitespace, truncated, trailing comma, extra data, BOM give JSONDecodeError (a ValueError). Deep nesting: F-1. Accepted by design: [] / null / "x" (verify_pack refuses non-objects at :257), 1e-999 (underflows to 0.0), lone surrogate string.
- verify_pack: 15 raw shapes (non-object, unsigned, signed as 1 or "true", signature or fingerprint missing or wrong type, blank or non-string signer, non-canonical or non-ASCII signature, valid signature on a non-BoardPack) all give PackVerificationError. Text echoes: first 16 characters of the two key fingerprints, the pydantic exception TYPE name only, and cryptography's generic message for an unusable key (seen: "Unable to load PEM file", "no BEGIN PUBLIC KEY"; other cryptography versions NOT checked). No caller field value is echoed.
- served_signing_from_env: never raised across 11 env shapes (unset, both set, signer only, key only, blank signer, missing file, directory, ".//./" and ".." and trailing-slash paths, non-ASCII name, junk PEM, non-ASCII content). /health key_error names the file's name only, never the configured path (window of cases above); the private PEM is not in repr().
- parse_period: Q0, Q5, q3, 0000-Q1, full-width and Arabic-Indic digits, NUL, empty, None all InvalidWindow; 9999-Q4 parses.
- normalise_bound: empty, blank, "Z", month 13, hour 25, +24:00, +99:99, "1e5", Arabic-Indic digits, 100000 characters, and out-of-range UTC instants all InvalidWindow. Accepted forms: F-3, F-4.
- resolve_window: blank period, blank since and blank until are each a 422, never all-time; period with since/until, and since after until (including a future-only since, because until defaults to generation time), are 422.
- HTTP: 18 inputs on /pack and /pack.html, 36 requests: no 500.

TEST GAPS (named files: tests/test_c4_window_and_signature.py, tests/test_f4_served_signing.py, tests/test_api.py)
Baseline: 135 passed. Line trace over signing.py and window.py: 2 lines never run, signing.py:220 (sign_pack JSON round-trip guard) and signing.py:263 (verify_pack missing signature/fingerprint guard). Line coverage only; compound conditions are not branch-covered. 27 mutants on the listed symbols: 22 killed, 5 SURVIVED the full suite:
  - signing.py:260 `is not True` -> `not raw.get("signed")`: no test for signed as 1 or "true". Defense in depth (only a key holder can sign such a payload).
  - signing.py:263 guard removed: a pack with no signature or fingerprint then dies with TypeError ('NoneType' not subscriptable) at the wrong-key message instead of the named refusal. The guard is load-bearing for the message and untested.
  - signing.py:279 validate=True removed: EQUIVALENT mutant, the canonical re-encode compare on the next line catches it (redundant defense).
  - window.py:80 strip on bounds: untested whitespace-padded since/until.
  - window.py:87 lowercase "z": untested; without it lowercase z is InvalidWindow (fail closed, the accept path is lost).
Mutation not run on served_signing_from_env beyond the 4 mutants that were killed (signer-only, key-only, blank signer, path redaction).

OVERLAP
- PR 317 head 9cc52212607105e7e0d0ac5c81b902810f197693: touches engine.py, README.md and one test in this service; no line of its engine.py diff mentions window, signing or InvalidWindow. merge-tree against main: clean.
- PR 383 head defb7eaf5c705a820471b1c8904d1f3c4d44d167: 20 files, in this service only api.py (a warn_open import and call at app creation). Does not touch the 422 path (:100). merge-tree against main: clean.
Heads read now through git; not re-reviewed here.

CONDITIONS (for the builder queue, not edits by me)
1. F-1: catch RecursionError in parse_pack_json; add a test.
2. Add tests for the five surviving mutants (or record the equivalent one).
3. Don's rulings: F-2 echo (strip or cap) and F-3 week/basic date forms (reject or document).

NOT VERIFIED: no GX10 run, no CI logs, Python 3.13.17 only, cryptography message text on other versions, Typer traceback locals (none shown in this environment), symlinked key file.

CONCLUSION: every malformed input I tried failed closed (4xx, named refusal or non-zero exit), and none gave a 500 or a pass. The exceptions to "named refusal" are F-1 (traceback) and F-5 (AttributeError, misuse only). The window can be silently narrowed by an accepted week form (F-3). Five behaviours are unpinned by tests. Confidence: HIGH on probed behaviour, MEDIUM on impact ratings.
