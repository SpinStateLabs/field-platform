# builder-6: condition fix on PR 409
PR 409 (branch fix/field-agent-read-cap-c642b, stacked on PR 372): old head 2c089ebb -> new head fdc2ec853742bc76d989e4722056c0bbbcd08f70 (one tests-only commit; author+committer Don Hagell noreply). Applies reviewer-2 C1 (and the mitigation named in its objection 2).
Added to tests/test_read_cap_c642b.py: chunks each below the cap but over it in total are refused; chunks totalling exactly the cap are accepted; the stream is not pulled past the chunk that crosses the cap. No source change.
Mutants: running total reset per chunk (S3) -> 2 tests FAIL (killed); check moved after the loop (buffers everything) -> the not-read-past-cap test FAILS (killed).
Ran (PYTHONUTF8=1, Windows): test_read_cap_c642b.py 11 passed; field-agent suite 214 passed, 1 skipped, canary subprocess test deselected (env: needs absolute PYTHONPATH in the child).
NOT done: C2 (the stack base PR 372 conflicts with main in docs/ENVIRONMENT.md and liveness.py, so 372 must be rebuilt first and 409 re-applied; I did not rebuild 372), C3 GX10 gate, C4 CI. Re-review requested on fdc2ec85.
