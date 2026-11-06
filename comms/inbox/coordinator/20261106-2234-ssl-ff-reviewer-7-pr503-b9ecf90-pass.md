# Review PR 503 (scout P-21: force-gateway hygiene judge refuses a NaN, infinite or non-number score) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `b9ecf90f4bc43b28df4a59316caf4a17a9ccfdd3` (no conditions beyond the standard CI and GX10 on the landed head; one behaviour change for Don below).

## Checks (HIGH, run by me)
- Identity: 3 commits (two work commits and a merge of main), author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 3; trailers Sonnet 5.5 (merge: none); .github/: 0 files. 3 files: force_gateway/hygiene_judge.py (+5), tests/test_hygiene_judge_scores.py (+79), docs/ENVIRONMENT.md (+3/-3, anchor rows). Merge base is current main 250154d3; a trial merge is clean.
- Code read: `clamp(x)` now raises `ValueError` unless `x` is a non-bool `int` or `float` that is finite; the surrounding `except Exception` already turns it into `HygieneJudgeError("unparseable judge output: ValueError")` (class name only); out-of-range finite values are still clamped to [0, 1]. Before: `float("nan")` clamped to 1.0 (a NaN `premise_rigor` read as perfect rigor, a NaN `sycophancy` as maximum), `true` became 1.0, `"0.5"` became 0.5; `json.loads` accepts the bare tokens NaN and Infinity, so a model reply can carry them. Other malformed inputs I traced: an overflow (`10**400`) or `int()` of a non-finite token in `usage` raises inside the same `try` and becomes the same named error.
- Tests on the exact head (Windows): test_hygiene_judge_scores.py 33 passed; `environment_anchors --check` 0 wrong rows. The PR also reports the whole force-gateway suite 481 passed (not re-run by me).
- Behaviour change, flagged by the PR and confirmed: a model that returns a numeric STRING ("0.5") for a score now yields the named error where it used to be accepted. The rubric asks for numbers; if live replies emit strings, relax that one case. For Don's call, not a defect.

## Mutants (14; counted from the table)
| # | mutant | result |
|---|---|---|
| C1 | check removed (old behaviour) | KILLED |
| C2 | `isfinite` dropped | KILLED |
| C3 | bool allowed | KILLED |
| C4 | numeric string allowed | KILLED |
| C5 | int refused (floats only) | KILLED |
| R1 | clamp upper bound removed | KILLED |
| R2 | clamp lower bound removed | KILLED |
| R3 | clamp bounds swapped | KILLED |
| R4 | a non-finite score clamps to 0.5 instead of raising | KILLED |
| S1 | `overall` not clamped | KILLED |
| S2 | `premise_rigor` not clamped | KILLED |
| S3 | `sycophancy` not clamped | KILLED |
| E1 | error text appended with the (fixed) exception text | SURVIVED (inconclusive: the appended text is the fixed "score is not a finite number", not a leak of caller data) |
| E2 | `except Exception` narrowed | SURVIVED (invalid mutant: my search string matched an earlier handler, not the one around the clamp, so it did not exercise the scoring path) |
Totals: 14 mutants, 12 killed, 2 survived (12+2 = 14); the two survivors are inconclusive or invalid as explained, not gaps I can attribute to the PR.

## Not verified
CI/GX10; Linux; the whole force-gateway suite on this head; how the scores gate behaviour downstream (the PR did not read it either).
