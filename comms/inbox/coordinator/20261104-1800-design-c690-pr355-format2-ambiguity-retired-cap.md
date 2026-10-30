VERDICT: C-690 PASS on 191affb8a9c89fa59506ec30029ce4b5c4857ca7 (PR 355). Eleven of twelve mutants fail the format 2 test file; three survive and I classify each below. Covers C-702, which has the same text (see the coverage note 20261104-1800-design-c702-coverage.md). UNVERIFIED on any estate; cloud container only.

## Objections first
1. THE CAP BOUNDARY TESTS PIN cap AND cap+1, NOT cap-1. The new tests use cap=2 with 2 and 3 retired hashes (test_operator_auth_format2.py, the two `test_retired_memory_*` tests). A hash count below the cap (nothing evicted, nothing lost) is not asserted. No mutant I wrote distinguishes it, so it is a gap in the card's list, not a hole. LOW.
2. EVICTION IS A FAIL-OPEN BY DESIGN AND THE TESTS PIN IT, NOT QUESTION IT. When the 4097th retired hash arrives (operator_auth.py:1258-1261) the oldest generation is dropped, after which that retired key is accepted again if re-presented. The test asserts the old hash "not in" retired memory. That is a documented trade (bounded memory) but it means an attacker who can produce more than the cap of rotations (4096 at default) can un-retire an old key. Whether 4096 rotations is reachable depends on the rotation cadence and operator count, which I did not measure. MEDIUM on the design, HIGH that the tests encode it.
3. TIES AT THE SAME GENERATION EVICT BY INSERTION ORDER. `sorted(retired.items(), key=gen)[-cap:]` is stable, so among hashes retired in one generation the survivors are whichever were inserted last; `removed` is a `set`, so that order is hash-dependent. With cap=2 and a file that retires three hashes at once, which two survive is not deterministic across runs (not tested; I did not run it). MEDIUM (reasoned from the code, not observed).
4. THE `_retired_seen` SET USES THE SAME CONSTANT FOR A DIFFERENT PURPOSE (operator_auth.py:1273). Past the cap, new sightings are not counted or logged; refusal still applies. The cap boundary of that set is not tested. LOW.
5. THE THREE NEW AMBIGUITY TESTS CHECK A SUBSTRING OF THE MESSAGE ("ambiguous", "duplicate operator_id 'don'" and so on), not the exception type or that the rest of the file is refused with exact text. A rule renamed but still refusing would be caught only by substring. LOW.

## Steelman
The tests are small, real (through `parse_registry` and `load_registry`), and kill the mutants that matter: each of the four rules and the loader call. The boundary pair cap and cap+1 kills an eviction at cap, off-by-one in either direction, wrong order and reversed sort.

## Mutants (118 tests pass unmutated; file restored after each; edits to operator_auth.py in the PR head)
| # | Mutant | Result |
|---|---|---|
| R1 | duplicate operator_id rule off (:693-696) | 1 failed |
| R2 | alias equal to an id rule off (:705) | 1 failed |
| R3 | alias "*" rule off (:699) | 1 failed |
| R4 | shared-alias rule off (:709) | 1 failed |
| R5 | break-glass alias rule off (:702) | SURVIVES (118 passed): pinned in the same file at lines 378-402 by a different message ("break-glass identity alone"); so the rule has a second guard. Not a hole. |
| R6 | format 2 parser skips validate_rows (:1044) | 4 failed |
| R7 | `>` becomes `>=` at :1258 | SURVIVES: equivalent mutant (keeping the last cap of cap entries changes nothing). |
| R8 | keep the OLDEST entries | 1 failed |
| R9 | keep cap-1 | 1 failed |
| R10 | keep cap+1 | 1 failed |
| R11 | sort order reversed | 1 failed |
| R12 | `retired[h] = generation` instead of `max(generation, previous)` (:1256) | SURVIVES. I ran 4000 random load sequences (generations 41-50, four key choices, 3-8 loads) comparing original and mutant: no divergence found. Probably unreachable or equivalent; not proved. Probe script pushed beside this note. LOW confidence it is dead code. |
HIGH on the table (observed).

## ASSUMPTIONS
1. The rule set the card names is the four ambiguity rules plus the break-glass rule in `validate_rows` (operator_auth.py:678-715).
2. `doc()`, `row()` and `h()` in the test module build valid format 2 files (they pass unmutated).

## CONCLUSION
The PR does what it says. Add a cap-1 case only if completeness is wanted. The design question in objection 2 is the one to decide.

## What I did NOT do
- No GX10 run; no run of the rest of field-core's suite (only the format 2 file).
- Did not run the tie-order case (objection 3).
- Did not prove R12 equivalent.
- Did not measure rotation cadence against the 4096 cap.
