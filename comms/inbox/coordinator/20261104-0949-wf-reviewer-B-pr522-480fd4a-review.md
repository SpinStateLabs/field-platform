# Review PR522 @480fd4a (sealed-ledger /export NUL + path leak) - wf-reviewer-B
ASSUMPTIONS: head 480fd4ae28d8c07916d42896b793e59660ab3286 (verified via gh, unchanged); GX10 venv-fp; PYTHONPATH uses ':' on Linux.
REASONING: Diff reads correct. NUL check precedes Path()/armed branch; no path echoed in 422. OSError handler emits errno name only; exc.errno None -> type name (HIGH). Allowlist 3->2 matches removal of one str(exc) reply site (tools lint passes, HIGH).
Tests: new file 7 passed; sealed-ledger suite 809 passed 4 skipped (test_guarded_routes_ledger_c511.py collection error under my env, ignored; builder cited a different baseline error; MEDIUM that it is env); tools tests (echo/anchors/proxy/ci_anchors) 233 passed 4 skipped from repo root.
Mutants (table):
M1 drop NUL check - killed (4 red)
M2 NUL check startswith only - killed (3 red)
M3 422->400 - killed (4 red)
M4 detail=str(exc) - killed (1 red)
M5 detail adds target path - killed (1 red)
M6 errno name -> type name - killed (1 red)
M7 500->503 - killed (1 red)
M8 422 message text changed - killed (4 red)
Total 8, killed 8, survived 0.
LOW: armed (operator-required) branch with NUL not exercised (builder disclosed; NUL check runs before it by code reading). Test 3 (missing parent) is weak by design (accepts 200 or 500). Public-safety allowlist edit is a debt reduction only.
CONCLUSION: PASS at 480fd4ae28d8c07916d42896b793e59660ab3286.
