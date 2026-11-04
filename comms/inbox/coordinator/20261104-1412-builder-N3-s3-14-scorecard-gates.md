# Builder B-S3-14: scorecard gate boundaries, draft PR 636

Head 67e347da on test/sentinel-scorecard-gate-boundaries (net diff: one new test file; commit 84292dea also added a stray empty file `services/conformance-sentinel/round`, from an unquoted `>` in my own shell echo; removed in 67e347da, history not rewritten). UNVERIFIED (no GX10).
- Tests only. 71 tests pass. Four mutants (catch >= to >, false-block <= to <, rate fallback 0.0 to 1.0, max_fb int to round) all killed; measure.py restored, no source change.
- FINDING (pinned, not fixed): zero conforming seeds gives false-block rate 0.0 and the false-block gate PASSES vacuously; gates_passed is True if catch passes. Separate card if wrong.
- markdown allowances int(n*0.05)/int(n*0.02) match the gate arithmetic for n=1..60,100,150,200 (and 1..399 in a probe): no mismatch.
- Ran: anchors 0 wrong; the four tools tests 261 passed (c57 green on current main now). NOT run: full conformance-sentinel suite, GX10.
