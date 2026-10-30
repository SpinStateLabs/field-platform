# C-429 reviewer report (Lane 5): PR 272 @56803e9 (C-426; my C-425 F-C425-1), tests only

VERDICT: PASS on the exact head 56803e9 (one commit directly on main 9589c82, which is current main; author and committer Don Hagell noreply). One test added, `test_a_rotation_event_without_a_segment_closed_is_refused` (+7, `services/sealed-ledger/tests/test_bundle_rotation_event_c407.py`); no production file touched. The mutant that survived at C-425 (a missing `segment_closed` read as matching) now goes red. Whole sealed-ledger suite on the head: 737 passed, 4 skipped (736 passed, 4 skipped at C-425's head: exactly the one new test). One LOW point. Class and file:line only.

OBJECTIONS FIRST
1. F-C429-1 LOW (PROVEN): the `segment_closed` comparison is still not pinned against a TYPE confusion: my mutant that compares `str(payload.get("segment_closed")) != str(v.archived_segments)` survives, so a rotation event carrying `"2"` (a string) where the integer 2 is expected would be accepted. The sibling comparisons are pinned for this (the `end_index` cases include `"7"` and `7.5`); `segment_closed` has wrong integers (1, 3, 0), None, and now a missing key, but no string or float. Impact: a forged rotation event with `"2"` instead of `2` passes this check; whether the bundle's other checks (spine, hashes, signature) already refuse a differently typed payload I did not probe. [HIGH on the survivor, LOW on exploitability]
2. The new test is the mirror of the existing "without an end_index" and "without a closed head" tests and uses the same relink helper, so it proves the check refuses a missing field and nothing else. That is the card's scope. [HIGH, read]

ASSUMPTIONS
1. Own GX10 worktree at the head (the merge base is the main tip, nothing to merge); the sealed-ledger package from its own directory with PYTHONPATH from its own and field-core's `src`; mutants by my runner on bundle.py 630-660 (7 hand; the file as judge; bytecode caching off). [HIGH]

REASONING
1. Diff: one test, `_forge_first_live_event(archived_bundle, lambda rec: rec["payload"].pop("segment_closed"))` then `not v.ok and v.first_failing_index == 8 and REASON in v.reason`, using the exact reason text and the failing index like its siblings. [HIGH, read]
2. Mutants (7 hand): killed 6. Killed: a missing `segment_closed` accepted via `.get(..., default)` (my C-425 survivor); a missing value accepted via `or`; the comparison removed; the comparison read with `[]` (a KeyError escapes and fails the test); and the sibling mutants for a missing `end_index` or `head_hash` still die. Survived: the string comparison (finding 1). [HIGH, run]
3. Tests: the file with test_export_bundle.py and test_witness.py: 182 passed; the whole sealed-ledger suite: 737 passed, 4 skipped. [HIGH, run]
4. C-425 F-C425-1 is closed. [HIGH]

CONCLUSION
PASS on 56803e9. Optional LOW card (coordinator numbers it): P1 builder: add `"2"` to the `segment_closed` wrong-value cases of `test_a_rotation_event_that_closes_another_segment_is_refused` (mutant: compare as a string). Note `2.0` is NOT a candidate: it equals 2 in Python, so the production comparison already accepts it, and a test asserting refusal would fail.

What I did NOT do: run CI (the coordinator's); probe whether another bundle check already refuses a string-typed `segment_closed`; Windows.
