VERDICT: C-711 PASS on 9cc52212607105e7e0d0ac5c81b902810f197693 (PR 317). `conformance_percent` equals an independent integer half-up rule on every pair I tried up to about 1e58 verdicts and refuses bad input as documented. Two precision-related mutants survive the test file because it checks ratios only up to 300. Both concern counts the ledger cannot hold today. UNVERIFIED on any estate; cloud container only.

## Objections first
1. THE TESTS CANNOT SEE A PRECISION OR FLOAT REGRESSION. The exhaustive test covers b up to 300 (test_conformance_rate_c138.py, `test_every_ratio_up_to_300...`). Mutant H7 (decimal precision 60 to 28) and mutant H16 (a float intermediate, `Decimal(100 * a / b)`) both leave all 42 tests green. By probe, the float-intermediate form is wrong on a near tie from about b = 1e16 (observed), and precision 28 would fail from about b = 1e26 by the same arithmetic (not run). The real code is correct to about b = 1e58 and wrong from b = 1e59 (observed: the "just below a tie" case rounds up). None of these counts is reachable from a ledger (the call site passes list lengths and their sum, engine.py:526-527), so this is a regression guard, not a live defect. LOW.
2. THE DECIMAL CONTEXT IS INHERITED. `localcontext()` copies the caller's context including traps. With the Inexact trap set on the current context, `conformance_percent(1, 3)` raises `Inexact` (observed). Nothing in the repository sets that trap that I saw; a host application that does would turn one metric into an exception. LOW.
3. THE INT CONTRACT ACCEPTS INT SUBCLASSES OTHER THAN BOOL. An `IntEnum` member is accepted (observed: 1 of 4 gives 25.0). The call site passes plain ints. LOW.
4. THE README'S "ALL FIVE VERDICT COUNTS" MATCHES THE CODE (engine.py:524-527: allows, blocks, escalates, shadow blocks, shadow escalates), but the rate's note text is built separately (engine.py:~528-531) from the same five values; the two are not tied by a test. LOW.
5. THE SIGNED-PACK STATEMENT IS NOT VERIFIED HERE. The README says a regenerated pack "can read 0.1 higher" and that the verifier does not re-derive the rate. I did not read the verifier. MEDIUM (not in source for me).

## Steelman
The rule is exact for every case that can occur, the .5 boundaries are pinned both through the function and through a full pack, the README's old and new printed values are right (observed: float `round` gives 6.2, 31.2 and 18.8 for 1, 5 and 3 of 16, so exactly the first two changed, as the README says), and the input contract is enforced for bool, float, string, None, negative and `allows > total`.

## Probes (script pushed beside this note)
- Near ties constructed as 1000a/b = 1.5 minus or plus 1/(2b) for b from 1e3 to 1e70: real function matches the integer rule through 1e58 on both sides; "below" mismatches from 1e59; the float-intermediate form is wrong on the "above" side from 1e16.
- 20000 random pairs with b up to 1e40: 0 mismatches.
- Contract: (0, 0) gives None; (1, 0), (-1, 5), (6, 5) give ValueError; True, 1.0, 4.0, "1" and None give TypeError.

## Mutants (42 tests pass unmutated; file restored after each)
| Mutant | Result |
|---|---|
| half-even, half-down, round-up, round-down, ceiling | 1 failed each |
| two decimals; precision 3; float `round()` | 1 failed each |
| precision 60 to 28 | SURVIVES |
| float intermediate (H16) | SURVIVES |
| bool allowed; non-int allowed; `allows > total` check dropped; `>=` refused; negative allowed | 1 failed each |
| no-verdicts returns 0.0 | 1 failed |
HIGH (observed).

## What I did NOT do
- No GX10 or estate run; no pack generated end to end.
- Did not read the pack verifier (objection 5) or the metric note builder.
- Did not run the decimal-precision-28 mutant against a b near 1e26 (reasoned).
