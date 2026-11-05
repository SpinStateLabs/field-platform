# Review PR 812 (rebuild of 555, spend-governor lone surrogate -> 422) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `abf5d4417d60fe0d72a560d5171d31c32eb4c46d` (no conditions; 2 optional LOWs for a NEW PR).

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. .github/: 0 files. Scope: api.py +3/-2, core.py +18/-4, usage.py +2/-2, new test file +67 (4 files).
- Rebuild fidelity: `git patch-id --stable` of the original da2054d6 == head commit == net diff vs main: all `8c6ee71ec291`. Identical patch.
- Base: merge-base IS current origin/main 3804d0b9 (the head is already on the m3-landed main; the PR text says 869cf2ed, stale but harmless).
- Prior verdicts on the original #555 exist on comms (reviewer-6 on da2054d, reviewer-3 on 55cb95c); same patch.
- Code read: `Utf8Str = Annotated[str, AfterValidator(_encodable)]`; refuses a lone surrogate with a fixed message (no echo); applied to /spend note, /usage note, cap currency and on_breach, allowed_models entries. I checked the remaining str fields in api.py/core.py/usage.py: agent_id, action, model, resolved_by, rate action/period carry min_length (pydantic already refuses a lone surrogate there, as the test docstring says); `source` is a Literal. No unbounded request text field missed (MEDIUM: grep of annotations, not a runtime probe of each).
- Tests on the exact head (Windows, PYTHONUTF8=1): test_lone_surrogate_text_422.py 6 passed.

## Mutants (10; table counted)
| # | mutant | result |
|---|---|---|
| A1 | /spend note plain str | KILLED |
| A2 | /usage note plain str | KILLED |
| A3 | Utf8Str = str (all fields) | KILLED |
| K1 | currency plain str | KILLED |
| K2 | on_breach plain str | KILLED |
| U1 | allowed_models plain str | KILLED |
| E1 | _encodable never refuses | KILLED |
| E2 | _encodable refuses all non-ASCII | KILLED |
| E3 | error message echoes the value | SURVIVED |
| E4 | _encodable returns '' for valid text | SURVIVED |
Totals: 10 mutants, 8 killed, 2 survived (8+2 = 10). All six per-field mutants are killed.

## Optional LOWs (new PR)
1. E3: nothing asserts the 422 body does not repeat the submitted text (the docstring promises it).
2. E4: the ordinary-Unicode test checks only status 201, not that the stored note round-trips.

## Not verified
CI/GX10 on this head. Whole spend-governor suite not re-run by me; the PR's one failing test (test_governor_store_concurrency) I saw fail identically on unmodified main earlier in this session (PR761 review).
