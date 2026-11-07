# Review PR #837 (G18: stage1_window, mechanical Stage 1 clean-window evaluation; conditions applied) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `c972adf47b608c8424b94bb1eb760784519d4fb4`. Reviewer 7's C1 (eight labels in both snapshots) and C2 (window end in the row, future window refused) are met. One new condition, small: the tool says it "fails closed", but a NaN timestamp or `--min-hours nan` makes any window clean (C1 below).

## Facts (HIGH, read from the head)
- 4 commits (`81fd0e2d`, `3a435b7a`, merge `fae56564`, `c972adf4`); every commit authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. Nothing under `.github/`. 3 files vs main: `tools/stage1_window.py` (+176), `tools/tests/test_stage1_window_g18.py` (+296), one runbook line (+1/-1).
- The head contains current main `ccd013d4` (merge-base is main's head); `git merge-tree --write-tree origin/main HEAD`: 0 conflict lines.
- The delta from reviewer 7's head to this head adds `REQUIRED_LABELS` (from `OPERATOR_BLOCK_SERVICES`; every label checked in both snapshots, "label: missing from the before|after snapshot"), `FUTURE_SKEW_SECONDS` (300; `evaluate_window(..., now)`), and `window_end` in the row. The runbook line now names the eight-service and future-date rules. No estate value in the added text.
- Boundaries I ran with a pinned clock: after = now+299 clean, now+300 clean, now+301 "the window ends in the future", 74 years ahead refused. A snapshot missing one label gives the named message plus the controller's `health_failure` and the two counter messages.

## Verification (run by me, Windows 10, Python 3.14)
- test_stage1_window_g18.py: 53 passed. `tools/environment_anchors.py --check`: 0 wrong anchor rows.
- Hand mutants (mine, 12, one at a time against the new file; restored, tree clean). Counted from the output: 10 RED, 2 survived. RED: label loop off; before side unchecked; after side unchecked; seven labels; future check off; skew a day; `now` argument ignored; row without `window_end`; `window_end` = window start; future check ahead of the length check changed.
  Survived: (a) the skew edge (`>` vs `>=` at exactly 300 s): my mutant subtracts 1e-9 from a number near 1.8e9, below float resolution, so it is an EQUIVALENT mutant, not a test gap; (b) the row's `services` count taken from the after snapshot instead of the before one (LOW: no test gives the two a different label count).
- CI on this head: all 7 jobs pass (compose-smoke, compose-upgrade-smoke, fly-image-smoke, tests 3.11 to 3.14).

## Condition
**C1 (MEDIUM-LOW, confirmed by running): a NaN timestamp or `--min-hours nan` defeats the fail-closed rule.** `json.loads` accepts `NaN`; a `taken_at` of NaN in either file passes every comparison in `evaluate_window` (`t1 <= t0`, the length test and the future test are all false for NaN), so the window is clean. On the CLI: both snapshots with `taken_at` NaN: `[PASS] the Stage 1 window is clean`, exit 0 without `--records`; with `--records` it prints PASS then dies with `ValueError: cannot convert float NaN to integer` at `int(after["taken_at"])` (no row written, by accident, but the PASS line is out). `--min-hours nan` passes a 1-second window (`args.min_hours < 0` is false for NaN). `-Infinity` as the before time also gives clean. Scope: the files are unsigned local JSON (the module says so), so a forger can already write a clean window; this is the accidental or malformed case, and a typo (`--min-hours nan`) the tool should refuse.
Fix: reject non-finite times and a non-finite `--min-hours` (`math.isfinite`), with tests (NaN, -inf, `--min-hours nan`), and print PASS only after the record decision (reviewer 7's LOW, still true: the PASS line precedes `refused: build_sha_invalid`).

## Optional (LOW)
1. Pin the row's `services` count against the before snapshot (survivor b).
2. The restock-masking limit (a restart that hides drops; reviewer 7 objection 1) is still not in the docstring.
3. Stage 2 does not read the G18 row yet (G25's card); PR 838 stacks on this one and needs its own rebase card.

## Not covered
GX10 on this head; Linux; a real snapshot of the eight services (my evidence is the unit tests plus probes on constructed snapshots).
