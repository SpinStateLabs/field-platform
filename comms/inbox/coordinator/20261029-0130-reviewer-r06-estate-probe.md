# R-06 reviewer report: tools/estate_probe.py (main a8bd47c)

Scope: all 804 lines read; AST mutants on the GX10 (`~/ff-work/r06_mut.log`), ranges 164-172, 258-262, 370-402, 424-432.

OBJECTIONS FIRST
1. A probe that can leave the canary killed can cause the outage it checks for.
2. A probe that infers "armed vs OFF" from the payload cannot fail a wrong mode.
3. A mutation score over four chosen ranges is partial, not a coverage claim.

ASSUMPTIONS
1. Main a8bd47c; tests are tools/tests/test_estate_probe.py as on main. [HIGH]
2. "Survived" = the tools test selection stayed green. [HIGH]

REASONING / FINDINGS
1. Redirect and proxy handling: sound (own opener, no env proxy, no redirect follow). [MEDIUM: read, not mutated]
2. LOW: `resp.read()` uncapped; a hostile or broken estate can stream unbounded data. [HIGH]
3. LOW: `cmd_catalogue` has no restore path; a mid-sequence failure leaves the canary killed (phase_g_check has `_settle_canary` and `--restore`). [HIGH]
4. MEDIUM: `check_status_pairing` infers armed-vs-OFF per payload, informational print only, no `--expect-mode`; a mis-set mode passes. [MEDIUM]
5. Mutation: 12 mutants (ranges 164-172 gave 0): 8 killed, 4 survived. [HIGH]
   - L261 `is_guarded` method compare `==`->`!=`: no test distinguishes method.
   - L377 bound `>=`->`>`: equal-count boundary untested.
   - L392 error branch `if`->False: untested.
   - L428 `got == "unknown"` ->`!=`: unknown-state branch untested.

CONCLUSION
No defect found that makes the probe pass falsely on the paths the current tests cover; 4 test gaps plus findings 2-4. Suggested fix card: `--expect-mode`, restore on `cmd_catalogue` failure, a read cap, four tests. Register rows F-R06-1..4 added (121 rows).
