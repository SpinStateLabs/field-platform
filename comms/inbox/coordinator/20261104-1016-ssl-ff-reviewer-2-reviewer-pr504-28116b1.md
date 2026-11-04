# Reviewer report: PR 504 @28116b1f (conformance-sentinel strict judge parse, scout P-20)

Reviewer: ssl-ff-reviewer-2. All runs UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH with ':' separator.

## Verdict: PASS WITH CONDITIONS (head 28116b1f5e006a0f8df433b91dd851e9e25736f3)
Conditions (not code): C1 rebase on current main (PR base is cd3b7690; main is now 97dcfec1, not re-checked for conflict with judge.py or ENVIRONMENT.md); C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking code finding.

## Objections first (HIGH = verified by run)
1. Class is `# pragma: no cover` (judge.py AnthropicJudgeClient): coverage will not flag a dead branch; only the tests guard it. Tests do reach it via an injected client (HIGH).
2. `bool` is a subclass of `int`; a lazy `isinstance(x,(int,float))` would accept true as 1.0. Pinned (B2 killed) (HIGH).
3. `float` of a huge JSON int raises OverflowError, `1e999` parses to inf. Both end as JudgeError (probed: OverflowError, ValueError) (HIGH).
4. engine.py:320 formats `({exc})` into the escalation reason, so any JudgeError text reaches the caller; the new messages are class name only (HIGH).
5. Pre-existing, out of scope: `rationale: null` becomes the string "None" (judge.py str(data.get("rationale",""))) (HIGH, not this PR).

## Scope and identity
3 files: judge.py (+17/-7 lines net), tests/test_judge_parse_strict.py (new, 87), docs/ENVIRONMENT.md (6 lines, anchors). 2 commits on cd3b7690; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head), test_judge_parse_strict.py: 30 passed. Full conformance-sentinel suite: 274 passed with tests/test_mode_message_c377.py ignored (typer missing in my env; collection error is environmental, not the PR).

## Mutants (judge.py, one at a time, test file test_judge_parse_strict.py, baseline 30 passed so every kill is a real failure)
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| A1 | conforming | restore bool() | KILLED |
| A2 | conforming | accept int via (bool,int) | KILLED |
| A3 | conforming | reject null | KILLED |
| A4 | conforming | `not in (True, False)` (0/1 pass) | KILLED |
| A5 | conforming | accept "true"/"false" strings | KILLED |
| A6 | conforming | inverted None guard | KILLED |
| B1 | confidence | isfinite removed | KILLED |
| B2 | confidence | bool accepted | KILLED |
| B3 | confidence | numeric type check removed | SURVIVED, EQUIVALENT (math.isfinite raises TypeError on str/None/list, still JudgeError; verified by reading) |
| B4 | confidence | refuse only NaN | KILLED |
| B5 | confidence | refuse only inf | KILLED |
| B6 | confidence | int refused | KILLED |
| B7 | confidence | `and` for `or` | KILLED |
| C1 | clamp | lower clamp removed | KILLED |
| C2 | clamp | upper clamp removed | KILLED |
| C3 | clamp | no clamp | KILLED |
| C4 | clamp | control, behaviour-preserving for the tested range | SURVIVED, EQUIVALENT BY DESIGN (control) |
| D1 | resolve_floor | isfinite removed | KILLED |
| D2 | resolve_floor | only NaN to default | KILLED |
| D3 | resolve_floor | only inf to default | KILLED |
| D4 | resolve_floor | non-finite to 0.0 | KILLED |
| D5 | resolve_floor | clamp removed | KILLED |
| D6 | resolve_floor | upper clamp removed | KILLED |
| D7 | resolve_floor | non-finite to 1.0 | KILLED |
| D8 | resolve_floor | unparseable to 0.0 | KILLED |
| E1 | error text | append `{exc}` to message | SURVIVED (real, LOW, see F1) |
| E2 | error text | echo upstream text | KILLED |
| E3 | error text | echo parsed data | KILLED |
| E4 | error text | generic except narrowed, ValueError escapes | KILLED |
| E5 | error text | prefix changed | KILLED |

Counted from the table: 30 rows (conforming 6, confidence 7, clamp 4, resolve_floor 8, error text 5). KILLED 27, SURVIVED 3 (B3 equivalent, C4 control, E1 real LOW). Kill rate on non-equivalent mutants: 27 of 28 = 96%.

## Findings
- F1 LOW (HIGH confidence): test_the_error_text_names_the_class_only asserts only that "nan" is absent. E1 (append `{exc}`) survives because the in-code ValueError texts are constants. Pin: assert `str(e.value)` equals `"judge returned unparseable verdict: ValueError"` for each parametrised bad value. Optional, new PR.
- F2 LOW (HIGH): ENVIRONMENT.md anchors are re-pinned by --fix; they will drift again on any judge.py edit; check passes at this head.

## Not verified
Rebase on 97dcfec1; CI; GX10; the live Anthropic path (declared-untested in the class docstring).
