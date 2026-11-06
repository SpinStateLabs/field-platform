# Review PR #744 (agent-registry: find_secrets and scan_secrets_text no longer quadratic, S7-14) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `af5dc04eac8dc9b9ffdf89fc88ac0ca551a9fa74`. This head is the follow-up to reviewer-3's PASS WITH CONDITIONS on `c97dd1cf` (comms/inbox/coordinator/20261105-1006-ssl-ff-reviewer-3-review-pr744-c97dd1c.md); its one MEDIUM finding is checked below.

## Facts (HIGH, read from the head)
- 2 commits (c97dd1cf, af5dc04e); 3 files: agent_registry/discover.py (+8/-4), agent_registry/redaction.py (+13/-3), tests/test_find_secrets_scale.py (new, 140 lines). Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The only change since reviewer-3's head is tests/test_find_secrets_scale.py (+23): a `_CountSpy(str)` subclass that records the span of every `count` call, and `test_scan_secrets_text_counts_each_character_for_newlines_at_most_once`.

## The code (read, with my own reasoning)
- `find_secrets` keeps accepted spans in two parallel sorted lists. Accepted spans never overlap, so their ends are sorted when their starts are; a candidate overlaps an accepted span iff `ends[i-1] > start` where `i = bisect_left(starts, end)` counts the spans starting before the candidate's end. That equals the old `any(start < t_end and t_start < end)` test. Zero-length spans (no pattern produces one: every pattern needs about a dozen characters) would also behave identically, including a touching span at the same start.
- `scan_secrets_text` counts newlines between hits (`line += text.count("\n", at, hit.start)`, `at = hit.start`) instead of from 0 per hit; the hits are in text order, so the spans tile the text.

## Reviewer-3's finding on this head
- Finding 1 (MEDIUM, mutant Q2: reverting `scan_secrets_text` to count from 0 per hit passed the wall-clock test): closed. The spy test sums the `count` spans and requires `<= len(text)` and `<= number of hits` calls on a 2,000-hit text; the old per-hit count sums to millions. Mutant Q2 is now RED (re-run by me).

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_find_secrets_scale.py: 5 passed (2.1 s).
- Full agent-registry suite (all service sources on the path): 315 passed, 1 failed. The failure is `tests/test_registry_store_concurrency.py::test_concurrent_reads_and_writes_return_and_persist_the_right_agent` ("8 worker thread(s) still running after 60 s: deadlock"). It fails the same way on main `250154d3` on this host (run alone, 133 s), and neither this PR nor reviewer-3's earlier run touches the registry store, so I treat it as a slow-host timing failure that this PR does not cause; I did not investigate it further.
- Mutants (mine, 11 hand mutants on discover.py and redaction.py, one at a time against the scale tests; files restored from backup, tree clean afterwards). Counted from the output: 9 RED, 2 SURVIVED.
  - RED: Q2 count from 0 again (the condition); line counter starts at 0; count skips a character; `at` never advances; count called twice per hit (the span bound refuses it); a whole-text count per hit; no overlap check in find_secrets; `bisect_right` for the end bound; touching spans counted as overlapping.
  - SURVIVED: `at = hit.end` instead of `hit.start` (equivalent: a matched value contains no newline, as reviewer-3 also found); the text converted to a plain `str` at the top of `scan_secrets_text` (the spy is then bypassed, `counted` is 0, and the assertions `counted <= len(text)` and `len(spans) <= len(hits)` still hold: a vacuous pass).

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. Assert `len(body.spans) >= 1` (or compare to the hit count) in the spy test, so it fails if the spy is ever bypassed by a conversion to plain `str`.

## Not covered
Linux; the pre-existing concurrency test failure above on a host where it passes; did not rebase on current main.
