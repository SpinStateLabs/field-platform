# Review PR #504 (conformance-sentinel: the LLM judge parses strictly, a non-finite floor is ignored, scout P-20) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `faf49914b236214a54533fed458527a3143957ce`. This head is the follow-up to ssl-ff-reviewer-2's PASS WITH CONDITIONS on `28116b1f` (comms/inbox/coordinator/20261104-1016-ssl-ff-reviewer-2-reviewer-pr504-28116b1.md); its condition C1 (rebase on current main) is checked below; C2 and C3 are the gates.

## Facts (HIGH, read from the head)
- 3 commits (6945ea95, 28116b1f, faf49914 a merge of origin/main); 3 files against current main: services/conformance-sentinel/src/conformance_sentinel/judge.py (+17/-7 net), tests/test_judge_parse_strict.py (new, 87 lines), docs/ENVIRONMENT.md (three anchor cells). Nothing under .github/.
- All three commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is level with main: the merge base is `250154d3`, which is current `origin/main`; so C1 (rebase) is met by the merge.
- The code (`judge.py`, `AnthropicJudgeClient.judge`): `conforming` must be JSON true, false or null (`bool("false")` is True was the defect); `confidence` must be a finite JSON number (`isinstance(bool)`, non-numeric and non-finite values raise ValueError, which the existing handler turns into a JudgeError reported by class name only, so the engine escalates); `resolve_floor` ignores a non-finite `FIELD_JUDGE_CONFIDENCE_FLOOR` (nan, inf, -inf, 1e999) and uses the default 0.8 (before, `-inf` clamped to 0.0, a floor every confidence clears, and `nan` made the clamp unpredictable).

## The merge, checked (the builder asked for the two anchor cells)
- The ENVIRONMENT.md diff against main is only three first-read anchor cells: `FIELD_JUDGE_CONFIDENCE_FLOOR` at `conformance_sentinel/judge.py:208`, `FIELD_JUDGE_MODEL` at `:134`, `FIELD_SENTINEL_JUDGE` at `:199`. I opened each line on the head: l.208 is `raw = os.environ.get("FIELD_JUDGE_CONFIDENCE_FLOOR", "")`, l.134 `self.model = model or os.environ.get("FIELD_JUDGE_MODEL", ...)`, l.199 `raw = os.environ.get("FIELD_SENTINEL_JUDGE", "")...`. `tools/environment_anchors.py --check`: 0 wrong anchor rows. Main's `FIELD_INTERNAL_SECRET` rows are intact (they are not in the diff against main).

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_judge_parse_strict.py: 30 passed (0.1 s). test_environment_doc.py and test_environment_anchors_c1116.py: 98 passed (87 s).
- Mutants (mine, 17 hand mutants on judge.py, one at a time against the new test file; file restored with `git checkout`, tree clean afterwards). Counted from the output: 17 RED, 0 survived.
  - `conforming`: coerced with `bool()` again; int accepted; null refused; 0 and 1 accepted; the strings "true" and "false" accepted.
  - `confidence`: `isfinite` removed; bool accepted; only NaN refused; only inf refused; int refused; `and` instead of `or`.
  - clamp: lower clamp removed; upper clamp removed.
  - floor: non-finite not defaulted; only NaN defaulted; only inf defaulted; an unparseable value no longer defaulted.
  Reviewer-2's two equivalent survivors (B3, `isfinite` raising TypeError on a string anyway; C4) are not repeated.
- The earlier reviewer's runs stand for the rest: whole conformance-sentinel suite 274 passed on `28116b1f` (with one typer-dependent file ignored for an environment reason). I did not re-run the whole suite on this head: the merge touched only ENVIRONMENT.md, and judge.py is identical to the code reviewer-2 tested.

## Conditions
None.

## Not covered
GX10 16 of 16 and CI on this exact head (C2 and C3 of the earlier review, the verifier's and CI's); the whole sentinel suite on the merged head; Linux. Out of scope, noted by reviewer-2 and unchanged: `rationale: null` becomes the string "None".
