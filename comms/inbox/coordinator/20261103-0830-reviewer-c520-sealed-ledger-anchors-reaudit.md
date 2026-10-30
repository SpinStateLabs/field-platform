VERDICT: PASS WITH CONDITIONS on main b929f12 (sealed-ledger anchors re-audit after C-468)

Card C-520 (standing post-merge re-audit, services/sealed-ledger, `load_anchors` raises on an absent anchors file, merged a9dc4f3), Lane 7. Read first, as the card says: the existing reports on this service and file (my PR 303 report C-482 20261102-0930, C-186 ledger anchors and bundle, C-378 anchors fail-closed, C-387 every-anchor, R-13). I tested only what they did not. Main at the time: b929f12. Not run on the GX10 (cloud session). Findings become cards.

Conditions: three LOW-MEDIUM findings (freshness, counting, and an untested first-run case); none changes the C-468 fix.

OBJECTIONS (before evaluation)
1. A verifier that checks the anchors it finds cannot tell that anchors are missing (truncation of the newest ones).
2. A count of "N anchors hold" that includes duplicates overstates assurance.
3. The first-run case (an anchor written on an empty ledger) goes through a special path that nothing may pin.
4. Files edited on another platform (a byte order mark, CRLF) can fail closed with an unhelpful message, or worse pass.
5. Concurrent appenders can tear an anchor line.

ASSUMPTIONS
A1. Callers: unchanged since C-482: `load_anchors` has no production caller; `verify_anchors` (cli.py:415, `ledger verify --anchors`) reads its own copy of the parse and is fail-closed.
A2. "Anchors" are off-box checkpoints (chain_length, head_hash, optional signature) that `verify --anchors` replays against the live chain.

REASONING
1. Suite: the whole sealed-ledger suite on main b929f12 (source paths on PYTHONPATH, Python 3.13): 744 passed, 5 skipped, 0 failed (156 s) (HIGH, run).
2. Mutants, named with the killing test (hand, 14 that compile, only the anchor tests selected by `-k anchor` for speed, first failure shown): `load_anchors` returning `[]` on an absent file: test_an_absent_anchors_file_raises_and_names_the_path; its blank-line filter dropped: test_an_existing_empty_file_is_an_empty_list_not_an_error; `verify_anchors` passing an empty anchors file: test_an_empty_or_blank_anchors_file_is_a_failure; passing an absent file: test_a_nonexistent_anchors_file_is_a_failure; an OSError not handled: test_an_anchors_path_that_is_a_directory_is_an_unreadable_failure; a parse error not handled: test_an_unparseable_anchors_file_is_a_failure_not_a_crash; the signature never checked: test_pre_rotation_anchor_still_verifies; a bad signature accepted: test_signed_anchor_tamper_detected; the chain-shrank check removed: test_anchor_closes_tail_truncation; the archived-position check removed: test_anchor_inside_really_archived_segment_is_explicit_failure; the missing-segment check removed: test_an_anchor_in_a_missing_live_segment_fails_as_missing; a hash mismatch accepted: test_real_scene4_anchor_signed_before_c2_still_verifies. 12 red / 14. Survivors: (a) an unsigned anchor with a key supplied: the branch removed, the run still fails through the signature-invalid path (equivalent in outcome, the message differs and no test pins either); (b) the genesis anchor skip (`if anchor.chain_length == 0: continue`) removed: NOT equivalent, see F-C520-3.
3. Probes (made-up ledgers in temp directories):
   - F-C520-1 freshness: two anchors (after 3 and after 5 events): `verify` OK, 2 checked. Delete the newest line from the anchors file: `verify` still OK, 1 checked (PROVEN). `verify_anchors` replays each anchor present; it has no way to know that later anchors were removed, so events after the newest surviving anchor are not covered by any anchor. There is no option for a minimum anchor count or a newest-anchor age. (My attempt to show an actual tail replacement was not valid because a rebuilt chain changes the prefix hashes too; I claim only that the verifier accepts the shorter file, which is the run above.)
   - F-C520-2 counting: the same anchor line repeated three times verifies "6 checked" for two real anchors; anchors in reverse order verify OK (7 checked); neither is checked for order or duplicates (PROVEN).
   - F-C520-3 first run: `write_anchor` on an EMPTY ledger writes an anchor with chain_length 0. `verify_anchors` skips chain_length 0 (anchors.py, `if anchor.chain_length == 0: continue`) and answers OK (1 checked). With the skip removed, the same verify fails with "anchor 0: position 0 (global index -1) is in archived segment None ... " because `hash_at(-1)` returns "archived": a misleading failure on the very first anchor of a new estate. Nothing in the test suite pins this (the mutant survives all anchor tests) (PROVEN).
   - Byte order mark: an anchors file with a UTF-8 BOM fails closed ("not a readable anchor file (JSONDecodeError)"); CRLF line endings verify OK (PROVEN). Fail-closed is right; the message does not name the BOM.
   - Concurrency: 8 threads times 100 `append_anchor_line` calls to one file: 801 lines, 801 parse (no torn line) (PROVEN, one process; two processes on a local file system use the same O_APPEND write).
   - Other odd paths: a symlink to /dev/null, a directory, an empty file: each a failure with a message naming the file (PROVEN).
4. First-run directory (the card's third point): `append_anchor_line` creates the parent directory and opens with "a"; `ledger anchor` and `ledger rotate --anchors` only append; nothing reads before writing, so a missing directory or file is not an error on a first run; `verify --anchors` on a path that does not exist yet is a failure by design (C-192) (HIGH, read and run).

FINDINGS
- F-C520-1 LOW-MEDIUM (PROVEN): `verify --anchors` does not detect removal of the newest anchors; the README's "history erased" guarantee therefore depends on the off-box copy being complete. Fix: an optional `--min-anchors N` or `--newest-after <time>` (and a sentence in the README), so an operator can assert freshness; default behaviour unchanged.
- F-C520-2 LOW (PROVEN): duplicate and out-of-order anchors are accepted and counted, so "OK - N anchor(s) hold" can overstate. Fix: require strictly increasing chain_length (or count distinct positions) and report the distinct count.
- F-C520-3 LOW-MEDIUM test gap (PROVEN): the genesis (chain_length 0) anchor skip is pinned by nothing; without it the first anchor of every new estate fails verification with a misleading message. Fix: one test: anchor an empty ledger, verify OK, append events, verify OK again.
- F-C520-4 LOW: the unsigned-anchor-with-a-key message is not pinned (survivor a); pin the message or drop the branch.
- F-C520-5 LOW (usability): a BOM-prefixed anchors file fails closed with a JSON error; add "byte order mark" to the message or strip it.

CONCLUSION: PASS WITH CONDITIONS on main b929f12. The C-468 change is correct and `verify_anchors` is fail-closed on every odd file I could make (absent, empty, a directory, a link to /dev/null, a BOM, garbage); the suite passes (744) and 12 of 14 mutants are red with the killing tests named. What the earlier reports did not cover: the verifier cannot see truncated anchors (F-C520-1), counts duplicates (F-C520-2), and its first-run case is untested (F-C520-3).

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13 only.
- Mutants ran only the anchor-named tests (`-k anchor`), not the whole suite per mutant; a survivor could be killed by a test whose name lacks "anchor", though the whole suite passes on the unmutated code.
- Did not run two OS processes appending at once, a signed-anchor freshness check (none exists), or the archive and bundle paths beyond what C-186 and C-387 covered.
- Did not examine the 5 skipped tests.
