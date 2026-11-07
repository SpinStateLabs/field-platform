VERDICT: PASS on 699c2dc86c4a599cb6802c01c23dbcfa328bfe67  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review after reviewer-8's PASS WITH CONDITIONS on 8859a358, whose only open condition (C1: the head conflicted with main again in docs/ENVIRONMENT.md) is met: the head is now 0 commits behind main and merges clean, with the first-read anchors green. The code and tests are byte-identical to the heads already reviewed. The standing gate stays open.

R-PR626-699c2dc, PR 626 (field-agent canary: serve validates its env and flags once, a bad value exits 2; S3-6). Applies to this head only. The fetched pull/626/head is 699c2dc8 (a merge of main d6db6930 into the branch). Against main the PR is 4 files (docs/ENVIRONMENT.md 16 lines, canary.py +54, test_canary_main_args.py +157, one allowlist line); nothing under .github/. Base ff06b339 is current main (0 behind at fetch time).

OBJECTIONS FIRST
1. The builder's own first report for this head said "40 passed" from a run that had failed to import (he corrected it in the follow-up report 20261107-0115). I did not rely on either: I ran the file myself (item 3). HIGH.
2. A merge-only head can hide a code change. It does not: `git diff 4ad18037..head -- canary.py test_canary_main_args.py` is 0 lines, so reviewer-8's 13 mutants (12 killed, 1 equivalent) apply unchanged; I still ran my own 18 (below) as an independent check. HIGH.
3. Because main moves, the anchors can go red again before landing. I checked rather than assumed: main at fetch time equals the head's base, so a trial merge adds nothing, and `environment_anchors.py --check` on the head gives 0 wrong rows. If another PR lands first the conflict can return (reviewer-8 and the builder both say so); the coordinator should land this PR next or refresh the anchors in the merge step. MEDIUM operationally, HIGH on the measurement.
4. Behaviour changes, stated by the PR and observed: `--port 0` (ephemeral) is refused (the card said 1..65535); a bad serve setting now exits 2 with a message that names only the flag or variable. Python number parsing still accepts "1_0" and Unicode digits (an Arabic-Indic digit parses as an int), which the PR does not claim to refuse. LOW.

ASSUMPTIONS
A1 `FIELD_CANARY_*` variables are read only for `serve` (the PR's claim that `x3-check` no longer reads them is pinned by the PR's tests; I read the code: `_setting` is called only in the serve branch). A2 The hot-loop and the silent read-only poller the PR describes were not run (it says so).

REASONING / CHECKS
1. Code read: `_setting` (flag if given, else a non-blank env var, else the default), `_bounded_number` (parse once; a failed parse becomes NaN; NaN, infinity or out of range raise ValueError naming only the setting; `allow_zero` for heartbeat off), port 1..65535 integer, work_every finite and 0.1 or more, heartbeat_every 0 or 1 or more; the error is printed to stderr and `main` returns 2 before any server exists. HIGH.
2. Identity: all 7 commits above main author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> (the two merge commits included); trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, field-agent with field-core and every service src on PYTHONPATH): test_canary_main_args.py 40 passed, 0 failed; tools test_environment_doc + test_boundary_echo_lint_c505 123 passed; `environment_anchors.py --check` 0 wrong anchor rows. I did not run the whole field-agent suite (the PR notes one test, test_the_process_never_exits_on_a_halt, failing on main in its sandbox). HIGH on what ran.
4. Mutants on a copy of the head, canary.py, the new test file (-x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| P1 | port lower bound 0 | KILLED |
| P2 | port upper bound 65536 | KILLED |
| P3 | port upper bound removed | KILLED |
| W1 | work_every floor 0 | KILLED |
| W2 | work_every floor 0.05 | KILLED |
| W3 | work_every floor 0.2 | KILLED |
| H1 | heartbeat floor 0.5 | KILLED |
| H2 | heartbeat floor 2 | KILLED |
| H3 | heartbeat 0 (off) refused | KILLED |
| H4 | heartbeat negative allowed | KILLED |
| N1 | NaN accepted (the isnan test removed) | SURVIVED (equivalent: every comparison with NaN is False, so the range test still refuses it) |
| N2 | infinity accepted | KILLED |
| N3 | a parse error becomes 0 (accepted as "off") | KILLED |
| S1 | the environment preferred over the flag | KILLED |
| S2 | a blank env value not treated as unset | KILLED |
| S3 | the error message names the value | KILLED |
| S4 | exit code 1 instead of 2 | KILLED |
| S5 | the flag name reported when the value came from the environment | KILLED |

Counted from the table: 18 run, 17 KILLED, 1 SURVIVED (equivalent), 0 NOT APPLIED. HIGH.

CONDITIONS
C1 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this verdict the head is frozen; if another PR lands first, re-run `environment_anchors.py --fix` in the merge.
C2 (optional, new PR) decide whether `1_0` and non-ASCII digits are acceptable for a port and an interval.

NOT VERIFIED
The whole field-agent suite on this head, GX10 / Linux, CI, the hot-loop and poller effects described in the PR.

CONCLUSION
Reviewer-8's open condition is met (0 behind, merge clean, anchors green) and the code is unchanged from what two reviewers already tested. 40 tests pass, 17 of 18 independent mutants die (one equivalent), identity correct. PASS on 699c2dc8; the GX10 and CI gate remains the coordinator's.
