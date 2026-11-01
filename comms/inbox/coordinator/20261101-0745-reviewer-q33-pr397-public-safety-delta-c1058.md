VERDICT PASS on 4128a3acd2e678e01d240a296de1f4c5f2bcf151 (PR 397, Q-33, Lane 15 reviewer; delta 68eab2f..4128a3a on my own C-1058 finding F-397-1; public-safety class; UNVERIFIED: cloud, no GX10, no CI logs)

Public repo: counts and file:line by class only, no names, figures or addresses.

OBJECTIONS (first)
1. This answers a finding I wrote (C-1058); I re-ran it with my own scan and mutants.
2. A placeholder is not an anonymiser: the invoicing skill still describes client-specific billing terms (invoice currency, cadence, a partner field) under "<Client A>" and "<Client B>"; whoever knows the clients can match them.
3. The new test is structural and covers two lines; it does not pin the class (named client, person, figure, mailbox, bank line) anywhere else in the file.
4. Removing text from the tree does not remove it from git history of a public repo (the C-563 option c ruling the builder cites; carried F-C408-3).
ASSUMPTIONS: head current (git ls-remote = full sha above); delta = two files: agents/ssl-invoicing-agent/SKILL.md (+2 -2) and tools/tests/test_invoicing_skill_placeholders_c1068.py (+30), git diff 68eab2f head --stat.

REASONING
1. Baseline: the new test file 2 passed (HIGH, run).
2. Class scan of the whole tree (named external organisations, a named external contact, a project or ticket identifier; case-insensitive; the test file excluded): main has 4 lines in agents/ssl-invoicing-agent/SKILL.md; at this head that file has 0 (HIGH, run). Elsewhere the class counts are identical on main and on the head: agents/ssl-timekeeping-agent/SKILL.md 11 lines, manifests/ssl-timekeeping-agent.yaml 2 lines (PR 408's scope, finding F-C408-1 of C-1076, still open there). Emails in the invoicing skill: 0 (HIGH, run).
3. The delta replaces the last named client and the two literal short codes in the description line and the code example with `<Client X>` and `<code X>` placeholders (HIGH, read of the diff).
4. Test power: 10 mutants on the skill file, run against the new test file. Killed (6): either description placeholder replaced by a name; a literal code back; a name back in the code example; a second "codes" line; and a mailbox added on the codes line (killed only because it edits the line the test reads). SURVIVED (4): a name replacing the placeholder on line 108 and on line 110; a figure replacing `<rate>`; a bank-detail line added elsewhere (HIGH, run). The builder's claim "a name back, a literal code back are red" is accurate for those two lines; the class is unpinned elsewhere in the file.
5. Builder's other items: F-397-2/-3 are carried by PR 408 (confirmed: PR 408's files are the timekeeping skill and manifests; no overlap); F-397-4 (STATE.md wording) was handed to the coordinator, not edited (HIGH: STATE.md is unchanged in the delta).
6. merge-tree: clean against main and with PRs 325, 348, 356, 369, 375, 394, 395, 399, 402, 405, 408.

FINDINGS
- F-Q33-1 LOW-MEDIUM: the test pins two lines, so a name, a figure or a bank line reintroduced anywhere else in the invoicing skill passes (four survivors). Replace with a structural check over the whole file: every `**...**` client heading and every "USD <n>" figure is a placeholder, no `@`, no digit run after "account"; or a deny-list kept outside the repository.
- F-Q33-2 INFO: client-specific terms remain under placeholders (objection 2); a ruling for Don whether placeholder-only is the line.
- Carried: F-C408-1 (11 named lines in the timekeeping skill and 2 in its manifest, PR 408); F-C408-3 / C-563 (history).

NOT VERIFIED: CI, GX10, git history, binary assets, the PR text.

CONCLUSION: PASS. F-397-1 is closed: the last named client and the literal codes are gone from the invoicing skill, and the two lines the test reads cannot regress. One LOW-MEDIUM test gap (class unpinned) and two carried items.
