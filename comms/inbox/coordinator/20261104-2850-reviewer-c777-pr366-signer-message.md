VERDICT: PASS WITH CONDITIONS on 82d56b29e5fe1d0033432b5cec44eb9c18a330d5 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the signer test file ran: 103 passed)

Head matches the card. One commit on main; author and committer are the no-reply Don Hagell identity. Files: services/compliance-crosswalk/tests/test_signer_sanitise_c252.py (+12) and the service README (one table cell re-worded). Test-only for code; no source change.

OBJECTIONS FIRST
1. The guarantee holds at the library level for the shapes the card names, PROVEN by probe on _checked_signer: bytes, nested list, dict, int, bool, float NaN, an object whose repr is the canary, a str subclass (clean, with a newline, with U+200B or a right-to-left override, with a 201-character canary, or whose string conversion returns the canary plus a NUL): the message names the type, a length, or a code point and position, never the value (a one-character code point is the most it shows, and only for a refused control or format character).
2. Shapes that still echo a value, PROVEN: (a) a class whose NAME carries the value (`type("CANARY...", (), {})()`, or a dict subclass so named): the message prints the type name, so it echoes. Pathological: a secret would have to be a class name. (b) a str subclass whose string conversion raises an error that contains the value: that error comes from the caller's own code and propagates unchanged; the library does not catch it. LOW.
3. THE HTTP LAYER STILL ECHOES, PROVEN: POST /pack with the signer given as a list or a dict returns a framework 422 whose body includes the offending value ("input" field), because the request model declares the signer as a string and the framework's validation error echoes the input. A secret placed in that field by mistake is reflected in the response (and in any proxy or access log of the body). The PR's test and its stated purpose are the library message only; the README row it edits ("Enforced in code") says generate_pack "raises" and does not claim the HTTP body. MEDIUM-LOW (the same class as C-651/C-712: validation errors echoing input).
4. The new test's canary looks like a real key: it begins with the well-known prefix of this vendor's API keys followed by a short tail. It is made up and too short to be valid, but a public repository's secret scanner or a reader will treat the pattern as a key, and the project's own convention (card C-584: "a made-up marker, never a key-shaped string") says not to. LOW-MEDIUM (public-safety convention; no real secret).
5. The README cell was re-worded with no code change (the C-396 table); I checked it reads as before plus the non-text shapes. LOW.
6. Overlap with slices 1 and 2 (PRs 361, 364): none in files (this PR touches compliance-crosswalk only); no conflict. It belongs to the same C-397 family (a test that kills a surviving mutant) but not the same code.

ASSUMPTIONS
A1 "Message" = the text of InvalidSigner raised by _checked_signer. A2 Probes call the private function and the HTTP route in process; markers are invented. A3 One interpreter.

REASONING
1. The function (evidence_pack.py:112-135): non-text -> message with the class name; blank -> fixed text; over the limit -> the length; a refused character -> code point and position. No value interpolated. HIGH.
2. Mutants (each alone, restored, worktree removed, nothing committed): the message echoing repr of the value -> 1 failed; str of the value -> 1; type name plus repr -> 1; type name plus the first 8 characters of the repr -> 1; the qualified module and class name -> 1. 5 of 5 red. HIGH.
3. Probe table and the HTTP probe: as in objections 1-3. HIGH.
4. Diff scan: no address, SHA, flag value, deploy status or credential; the canary is key-SHAPED (objection 4), not a key. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The test pins the message against five echo mutants and the library never echoes a value. Two gaps outside the test's scope remain: the HTTP 422 echo and a key-shaped canary. Conditions, none blocking:
- C1 F-C777-1: make the HTTP route's validation errors drop input values (as the registry service does) or state in the README that the HTTP body echoes a non-text signer.
- C2 F-C777-2: use a non-key-shaped marker in the test (the project convention).
- C3: note that a class name is echoed (acceptable) in the helper's docstring.

FINDINGS
F-C777-1 MEDIUM-LOW, services/compliance-crosswalk/src/compliance_crosswalk/api.py:53 (signer: str) and the /pack route (framework 422 echoes a non-text signer). PROVEN.
F-C777-2 LOW-MEDIUM, services/compliance-crosswalk/tests/test_signer_sanitise_c252.py (canary shaped like a vendor key). PROVEN by reading.
F-C777-3 LOW, services/compliance-crosswalk/src/compliance_crosswalk/evidence_pack.py:118 (a class name carrying a value is echoed; a raising str subclass propagates the caller's own error). PROVEN (pathological).

NOT VERIFIED: CI; other routes that accept a signer (the CLI path); the rest of the crosswalk suite.
