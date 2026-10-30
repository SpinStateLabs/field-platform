# C-436 reviewer report (Lane 5): PR 279 @f28b368 (C-432; my C-429 F-C429-1), tests only

VERDICT: PASS on the exact head f28b368 (one commit directly on main 85c6cfd, current main; author and committer Don Hagell noreply). One line changed in `services/sealed-ledger/tests/test_bundle_rotation_event_c407.py` (+1 -1): the wrong-value cases of the `segment_closed` test grow from `[1, 3, 0, None]` to `[1, 3, 0, None, "2", True, [2]]`. No production file touched. The mutant I named at C-429 (comparing `segment_closed` as a string) now goes red. The file: 31 passed; the whole sealed-ledger suite on the head: 740 passed, 4 skipped. One LOW note. Class and file:line only.

OBJECTIONS FIRST
1. F-C436-1 LOW: of the three new cases only `"2"` is a real type-confusion probe. `[2]` is refused by any comparison (a list never equals 2, and a string comparison of `"[2]"` and `"2"` also differs), so it adds no discriminating power. `True` is refused only because the fixture's expected value is 2 and `True` is 1; with one archived segment the production comparison (`!=`) would accept `True` (Python: `True == 1`), so the case pins nothing about booleans on this fixture. Neither is wrong; they are harmless extra cases, and the card's mutant is killed by `"2"`. A bool-as-int acceptance is a property of Python equality in `bundle.py`, and no fixture here would exercise it. [HIGH, run]
2. `2.0` is still accepted by production (`2.0 == 2`); the PR rightly does not assert its refusal (I withdrew that suggestion at C-429). [HIGH]

ASSUMPTIONS
1. Own GX10 worktree at the head (the merge base is main's tip, nothing to merge); the sealed-ledger package from its own directory with PYTHONPATH from its own and field-core's `src`; mutants by my runner on bundle.py 630-660 (7 hand; the file as judge; bytecode caching off). [HIGH]

REASONING
1. Diff: only the parametrize list of `test_a_rotation_event_that_closes_another_segment_is_refused`; the body still forges the first live event with `segment_closed=<value>`, relinks the bundle and asserts `not v.ok`, `first_failing_index == 8` and the exact reason text. [HIGH, read]
2. Mutants (7 hand): killed 6: the string comparison of both sides (my C-429 survivor); `int()` coercion of the payload value; a string of the payload value against the integer; a one-element list unwrapped before the comparison; the comparison removed; a missing value accepted. The survivor is a bool-to-int normalisation mutant of mine, which is equivalent on this fixture (`int(True)` is 1, still different from 2). [HIGH, run]
3. Tests: the file 31 passed; the whole sealed-ledger suite 740 passed, 4 skipped (737 at C-429's head plus tests merged to main since). [HIGH, run]
4. C-429 F-C429-1 is closed. [HIGH]

CONCLUSION
PASS on f28b368. No card proposed; the redundant `[2]` and `True` cases can stay.

What I did NOT do: run CI (the coordinator's); probe whether another bundle check already refuses a string-typed `segment_closed`; Windows.
