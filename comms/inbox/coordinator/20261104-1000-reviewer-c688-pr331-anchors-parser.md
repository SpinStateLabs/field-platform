VERDICT: PASS WITH CONDITIONS on 1a45db00bcbf6c20828e7bc757d81a07ecbc8e18 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's test file ran: 26 passed)

The card named head cdea6de; the PR head is now 1a45db0 (two commits on main: cdea6de, then 1a45db0 "--min-anchors needs the public key"). Both read. Author and committer of both are the no-reply identity. 4 files: sealed_ledger/anchors.py, cli.py, README, tests/test_anchors_c573.py (+295). Earlier read: C-600 (on cdea6de).

OBJECTIONS FIRST
1. "Strict" is not fully strict: the parser splits on every Unicode line break (splitlines), so two valid records separated by U+2028 are read as two records, and the old parser did the same. Probe: parsed 2. The text says "one JSON object per non-blank line"; this is a record a human would not see as separate. LOW.
2. Field coercion is lax: chain_length "3" (a string) and 3.0 (a float) are accepted and verify as position 3 (pydantic lax mode); True is read as 1. With signatures the signed bytes differ so a forgery is not possible, but an unsigned file can carry these spellings. LOW.
3. A negative chain_length is accepted by the parser and fails verification with a misleading text ("position -1 ... is in archived segment None"); fail-closed, wrong reason. Same text path on main. LOW.
4. The floor still depends on the file being complete (stated in the docstring): removing the newest anchors passes without --min-anchors, by design and documented.
5. Process: --min-anchors without --anchors or --pubkey exits 2 only AFTER the chain walk and the event-signature checks have run and printed (cli.py:418-421), so a usage mistake is reported after expensive work and after OK lines. LOW.
6. One mutant survives (below); it is equivalent in practice but shows the floor test does not distinguish "signature-verified positions" from "all positions".

ASSUMPTIONS
A1 "Parses differently from the old parser" = the old code was the inline list comprehension removed in the diff (decode, splitlines, json.loads, model_validate); the new parser differs only by the BOM strip (anchors.py:94-102). A2 Probes ran on the real ledger store with three events; keys were generated for the test, nothing real used.

REASONING
1. Parser differences (probe table, parse_anchors): plain file 1 record; UTF-8 BOM + file 1 record (new behaviour: old failed); double BOM, BOM in the middle, UTF-16 BOM, NUL byte, two records on one line, an extra field: each raises (JSONDecodeError, UnicodeDecodeError or ValidationError); BOM only, empty, blank lines: 0 records, then verify_anchors fails with "holds no anchor records"; CRLF and no trailing newline: parsed. HIGH.
2. Truncated or empty file: a truncated last line raises and verify_anchors returns a failure ("not a readable anchor file"); an empty file fails (anchors.py:150-152). A file truncated at a line boundary is not detectable without --min-anchors (objection 4). HIGH.
3. Order and genesis (anchors.py:162-175, 187-191): lower chain_length after a higher one fails; two anchors at one position with different hashes fail; a repeat of the same pair is accepted and counted once in distinct_positions; a position-0 anchor without the genesis hash fails even with no key. The genesis constant is the same one write_anchor uses (anchors.py:86), so a legitimate empty-ledger anchor passes. HIGH.
4. Floor (anchors.py:129-136, 223-231): refused without a key; counts only positions whose record passed signature and chain checks; a position-0 record counts only with the genesis hash. Reached only after all other checks, so any earlier failure wins. HIGH.
5. Mutants (restored; worktree removed; nothing committed): order check off -> 1 failed; BOM strip off -> 2 failed; genesis check off -> 1 failed; key requirement for the floor off -> 1 failed; same-position-different-hash check off -> 1 failed; floor counts all positions instead of verified ones -> 26 passed (survives; equivalent today because with a key every reached anchor is both counted and in the set, but the test would not catch a future divergence).
6. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The parser is one function used by both paths, the new checks are sharp and each has a red test; remaining gaps are low-severity strictness points. Conditions, none blocking:
- C1 F-C688-1/-2: tighten the parser to strict types and to "\\n" lines, or state the leniency in the docstring and README.
- C2 F-C688-4: move the --min-anchors usage check before the chain walk.
- C3 F-C688-3 and the surviving mutant: one test where the floor distinguishes signed from unsigned positions, and a test for a negative position's message.

FINDINGS
F-C688-1 LOW, services/sealed-ledger/src/sealed_ledger/anchors.py:94-102 (splitlines splits on U+2028 and other breaks). PROVEN.
F-C688-2 LOW, anchors.py:38 (chain_length lax coercion from "3", 3.0, True). PROVEN.
F-C688-3 LOW, anchors.py:196-203 (negative position reports "archived segment None"). PROVEN.
F-C688-4 LOW, services/sealed-ledger/src/sealed_ledger/cli.py:418-421 (usage error after the heavy work). HIGH.
F-C688-5 INFO, tests/test_anchors_c573.py (floor mutant survives). PROVEN.

NOT VERIFIED: CI; the full sealed-ledger suite; the CLI exit codes end to end (read, not run); concurrency between a writer and verify.
