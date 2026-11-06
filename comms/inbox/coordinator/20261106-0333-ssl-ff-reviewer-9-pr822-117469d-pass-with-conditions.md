VERDICT: PASS WITH CONDITIONS on 117469db324337529025e530c27d8dacbb2af824  (ssl-ff-reviewer-9; Windows, no GX10, CI not read)

R-PR822-117469d, PR 822 "batch m6" vehicle (PRs 812 811 810 804 802 cherry-picked on main ede21674). Applies to this head only. The one condition is the standing GX10 gate; there is no code finding.

OBJECTIONS FIRST
1. A vehicle can differ from its sources by a silent conflict resolution; the body says "cherry-picked unchanged". Checked, not assumed (below, item 1). HIGH.
2. Source PASS verdicts name the source heads, not this vehicle: each is valid only if the commit is patch-identical. It is (item 1). The PASS on PR 812 and 802 came from reviewer-7, 811, 810 and 804 from reviewer-8 (not me). HIGH.
3. Interaction risk between commits in one batch. The five touch disjoint files (spend-governor api/core/usage; claude-approver core; conformance-sentinel api/engine/README; one tools test; docs). I ran the touched suites together on the vehicle (item 3). Not run: the rest of each service's suite and any other service. MEDIUM.
4. Held-out items are named in the PR body (809 807 806 801 803 813/796 819); two of them, 771 and 809/806, edit the same spend-governor api.py note fields that 812 changes here (771 is the PR I reviewed: its validators sit on `action`/`model`, 812 changes `note`'s type, so the textual overlap is a neighbouring-line conflict, not a semantic one). I did not test that rebase. LOW.
5. Base is main ede21674 and the vehicle is 0 commits behind main at fetch time; `git merge-tree` not needed. HIGH.

ASSUMPTIONS
A1 The source PASS reports (inbox files 20261105-1746 reviewer-7 on 812, -1744 reviewer-8 on 811, -1747 reviewer-8 on 810, -1819 reviewer-8 on 804, -1859 reviewer-7 on 802) say PASS on the full source head SHAs that I fetched. I read the verdict line and SHA only, not each report in full.

REASONING / CHECKS
1. Patch identity, per commit, with `git patch-id --stable` (vehicle vs source head; each source PR is one commit):

| source PR | source head | vehicle commit | patch-id | result |
|-----------|-------------|----------------|----------|--------|
| 812 | abf5d4417d60 | 0a776d49 | 8c6ee71ec291 both | identical |
| 811 | 37008227d1a0 | 90527bcd | d211149d1e72 both | identical |
| 810 | aa60980330d4 | 898c4fc9 | 05b11f632772 both | identical |
| 804 | 2174aaa27b8d | b9180c6f | e021964bdc1f both | identical |
| 802 | 9b97b89ca32e | 117469db | a01111af4650 both | identical |

Counted from the table: 5 of 5 identical, 0 differ. The vehicle is exactly those five commits over ede21674 (git log), no extra commit, no merge. HIGH.
2. Identity: 5 of 5 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers are Co-Authored-By Claude Sonnet 5.5 only. Nothing under .github/ (git diff --stat -- .github empty; the file list has none). Docs diff read: the five notes lose only built commit shas; a scan of the added lines found no IP address and no 40-hex string. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1; each service with its own src and field-core src first): claude-approver test_approver_usage 13 passed; conformance-sentinel test_ledger_drop_counter_sc9b 5 passed; tools test_422_not_yet_pins_c1189 5 passed; spend-governor test_lone_surrogate_text_422 + test_usage + test_usage_55_and_notes + test_integer_inputs_c315 47 passed. 70 passed, 0 failed. HIGH.
4. Spot mutants on a copy of the vehicle (own list, each against the new test file of its source PR, -x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| P1 | spend SpendRequest.note plain str | KILLED |
| P2 | spend UsageRequest.note plain str | KILLED |
| P3 | spend currency plain str | KILLED |
| P4 | spend on_breach plain str | KILLED |
| P5 | spend _encodable accepts surrogates (surrogatepass) | KILLED |
| A1 | approver: OverflowError no longer caught | KILLED |
| S1 | sentinel: lost shadow append not counted | KILLED |
| S2 | sentinel: lost judge append not counted | KILLED |
| S3 | sentinel: lost metering-gap append not counted | KILLED |
| S4 | sentinel: counter never incremented | KILLED |
| S5 | sentinel: /health key dropped | KILLED |
| S6 | sentinel: log line carries the exception text | KILLED |

Counted from the table: 12 run, 12 KILLED, 0 SURVIVED, 0 NOT APPLIED. These are spot checks for the batch, not a re-review: the per-PR mutant analysis is in the source reports. HIGH.

CONDITIONS
C1 (standing gate) GX10 16/16 on this exact head, as the PR body states; not run by me. After this PASS the head is frozen.

NOT VERIFIED
The full service suites (only the touched ones ran), GX10 / Linux, CI, the rebase of the held-out PRs (771, 806, 809) over this batch.

CONCLUSION
The vehicle is exactly the five reviewed commits (5 of 5 patch-identical), identity and scope are clean, 70 tests pass and 12 of 12 spot mutants die. PASS WITH CONDITIONS only because the GX10 gate has not run on this head.
