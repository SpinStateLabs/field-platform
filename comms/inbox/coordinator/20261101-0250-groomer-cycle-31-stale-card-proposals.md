# Groomer cycle 31 (Lane 9): stale-card proposals for the coordinator (UNVERIFIED: no GX10, no CI; read, not measured)

I did not edit TASK-QUEUE.md. Evidence: GitHub PR API read at 2026-11-01 ~02:50Z (409 PRs: 144 merged, 182 closed unmerged, 83 open) and the report files named below on `comms` at 620e189. Scanned 234 OPEN/CLAIMED/TAKEN card lines (PR 57, HOLD and Don-ruling lines skipped, 12 lines).

## Objections / limits (read first)
1. A report naming a card id proves the card was answered, not that the verdict is still current for the PR head; I flip nothing and propose only.
2. Claim lines carry a date, not a time, and several dates run past the container clock (Nov 4 to Nov 8 against Nov 1 02:50Z). The 3-hour inactivity test cannot be applied to them; no card is proposed stale on claim age alone.
3. FAIL verdicts below (C-782, C-785, C-787, C-807, C-860, C-866, C-883) close the reviewer card, not the PR: the conditions cards exist separately or still need cutting.

## A. CLAIMED/OPEN -> DONE (verdict in report) : 124 cards
Rule used: an inbox file named `*-reviewer-c<id>-*` or `*-design-c<id>-*` exists and its first 1500 bytes carry a verdict word. UNVERIFIED = cloud-only report.

| Card | Verdict | Report (comms/inbox/coordinator/) |
|---|---|---|
| C-712 | PASS WITH CONDITIONS | 20261104-1800-reviewer-c712-pr349-introspection-leak.md |
| C-756 | UNVERIFIED | 20261104-2010-reviewer-c756-audit-unverified-cloud-reports.md |
| C-769 | PASS WITH CONDITIONS | 20261104-2650-reviewer-c769-pr339-innerhtml-audit.md |
| C-781 | PASS WITH CONDITIONS | 20261030-1914-reviewer-c781-pr368-field-mcp-pr1.md |
| C-782 | FAIL | 20261030-1916-reviewer-c782-pr369-perimeter-tier-keys.md |
| C-784 | PASS WITH CONDITIONS | 20261030-1919-reviewer-c784-pr373-spend-totals-422.md |
| C-785 | FAIL | 20261030-1925-reviewer-c785-pr372-sdk-errors-no-body.md |
| C-786 | PASS WITH CONDITIONS | 20261030-1928-reviewer-c786-pr371-manifest-ref-id-grammar.md |
| C-787 | FAIL | 20261030-1945-reviewer-c787-pr370-compose-conditions.md |
| C-789 | PASS WITH CONDITIONS | 20261030-1948-reviewer-c789-pr344-cli-clients-no-proxy.md |
| C-792 | PASS WITH CONDITIONS | 20261105-1000-reviewer-c792-pr330-conditions-merge-order.md |
| C-795 | PASS WITH CONDITIONS | 20261105-1100-reviewer-c795-pr369-per-tier-keys-conditions.md |
| C-796 | PASS WITH CONDITIONS | 20261030-1958-reviewer-c796-pr347-edge-block-shapes.md |
| C-798 | PASS WITH CONDITIONS | 20261105-0600-design-c798-pr353-conditions.md |
| C-799 | PASS WITH CONDITIONS | 20261030-2002-reviewer-c799-pr366-signer-message-after-c777.md |
| C-800 | PASS WITH CONDITIONS | 20261105-1200-reviewer-c800-pr365-http-client-conditions.md |
| C-807 | FAIL | 20261030-2002-reviewer-c807-pr371-narrowed-head.md |
| C-850 | PASS WITH CONDITIONS | 20261105-1300-reviewer-c850-pr351-operator-key-limits.md |
| C-851 | PASS WITH CONDITIONS | 20261105-1400-reviewer-c851-pr352-new-head-c28167c.md |
| C-852 | PASS WITH CONDITIONS | 20261030-2011-reviewer-c852-pr355-format2-cap-fdc299c.md |
| C-853 | PASS WITH CONDITIONS | 20261030-2013-reviewer-c853-pr360-burst-boundary-window-start.md |
| C-854 | PASS WITH CONDITIONS | 20261105-1500-reviewer-c854-batch-by-pr376.md |
| C-855 | PASS WITH CONDITIONS | 20261030-2019-reviewer-c855-pr372-after-c785.md |
| C-856 | PASS WITH CONDITIONS | 20261105-1600-reviewer-c856-pr373-spend-totals-after-c784.md |
| C-857 | PASS WITH CONDITIONS | 20261030-2021-reviewer-c857-pr375-verifier-prefix-rule.md |
| C-858 | PASS WITH CONDITIONS | 20261105-1700-reviewer-c858-pr356-reconcile-newest-head.md |
| C-859 | PASS WITH CONDITIONS | 20261030-2023-reviewer-c859-pr374-pr369-authn-together.md |
| C-860 | FAIL | 20261030-2023-reviewer-c860-pr371-newest-head.md |
| C-861 | PASS WITH CONDITIONS | 20261030-2024-reviewer-c861-pr344-newest-head.md |
| C-862 | PASS WITH CONDITIONS | 20261030-2033-reviewer-c862-pr330-open-conditions-merge-order.md |
| C-863 | PASS WITH CONDITIONS | 20261105-1800-reviewer-c863-pr359-read-caps-newest-head.md |
| C-865 | PASS | 20261030-2037-reviewer-c865-pr317-pr318-heads-and-verdicts.md |
| C-866 | FAIL | 20261105-2000-reviewer-c866-audit-newest-cloud-reports.md |
| C-868 | PASS WITH CONDITIONS | 20261030-2040-reviewer-c868-pr346-commit-identity-ef19210.md |
| C-872 | PASS WITH CONDITIONS | 20261030-2042-reviewer-c872-pr379-runbook-scrub.md |
| C-873 | PASS WITH CONDITIONS | 20261030-2044-reviewer-c873-pr376-batch-by.md |
| C-875 | PASS WITH CONDITIONS | 20261030-2051-reviewer-c875-pr377-ntfy-runbook.md |
| C-878 | PASS WITH CONDITIONS | 20261030-2056-reviewer-c878-pr380-write-process-vs-369-374.md |
| C-879 | PASS WITH CONDITIONS | 20261030-2057-reviewer-c879-pr325-dead-code-readers.md |
| C-880 | PASS WITH CONDITIONS | 20261030-2103-reviewer-c880-pr356-vs-c858.md |
| C-881 | PASS WITH CONDITIONS | 20261030-2112-reviewer-c881-pr359-read-caps.md |
| C-882 | PASS WITH CONDITIONS | 20261030-2129-reviewer-c882-pr375-newest-head.md |
| C-883 | FAIL | 20261030-2124-reviewer-c883-pr371-id-grammar-containment.md |
| C-884 | PASS WITH CONDITIONS | 20261030-2135-reviewer-c884-pr372-newest-head.md |
| C-885 | PASS WITH CONDITIONS | 20261030-2142-reviewer-c885-pr373-newest-head.md |
| C-886 | PASS WITH CONDITIONS | 20261030-2149-reviewer-c886-pr363-video-script-newest-head.md |
| C-887 | PASS WITH CONDITIONS | 20261030-2155-reviewer-c887-pr369-newest-head.md |
| C-888 | PASS WITH CONDITIONS | 20261030-2204-reviewer-c888-pr383-startup-open-warning.md |
| C-889 | PASS WITH CONDITIONS | 20261030-2208-reviewer-c889-pr355-after-c847.md |
| C-890 | PASS WITH CONDITIONS | 20261030-2217-reviewer-c890-pr358-pr360-pr362-after-lane13.md |
| C-891 | PASS WITH CONDITIONS | 20261030-2224-reviewer-c891-pr365-pr367-after-lane13.md |
| C-892 | PASS WITH CONDITIONS | 20261030-2227-reviewer-c892-batch-by-pr376-vs-sources.md |
| C-893 | PASS WITH CONDITIONS | 20261030-2234-reviewer-c893-pr351-operator-key-limits.md |
| C-896 | PASS WITH CONDITIONS | 20261030-2248-reviewer-c896-pr374-after-c849.md |
| C-897 | PASS WITH CONDITIONS | 20261030-2304-reviewer-c897-pr356-rulings-c895.md |
| C-898 | PASS WITH CONDITIONS | 20261030-2308-reviewer-c898-pr384-vs-pr380-mcp-writes.md |
| C-899 | PASS WITH CONDITIONS | 20261030-2313-reviewer-c899-pr385-compose-resolved-followup.md |
| C-900 | PASS WITH CONDITIONS | 20261030-2316-reviewer-c900-pr387-compose-nonstring.md |
| C-901 | PASS WITH CONDITIONS | 20261030-2317-reviewer-c901-pr386-batch-bz.md |
| C-903 | PASS WITH CONDITIONS | 20261030-2329-reviewer-c903-pr384-vs-c869.md |
| C-904 | PASS WITH CONDITIONS | 20261030-2323-reviewer-c904-pr316-console-headers.md |
| C-905 | PASS WITH CONDITIONS | 20261030-2332-reviewer-c905-pr387-pr385-compose-class.md |
| C-906 | PASS WITH CONDITIONS | 20261030-2331-reviewer-c906-pr379-deploy-runbook-delta.md |
| C-907 | PASS WITH CONDITIONS | 20261030-2333-reviewer-c907-pr383-startup-warning-head.md |
| C-908 | PASS WITH CONDITIONS | 20261030-2336-reviewer-c908-pr349-revoke-newest-head.md |
| C-910 | PASS | 20261030-2338-reviewer-c910-pr340-pr341-newest-heads.md |
| C-940 | PASS WITH CONDITIONS | 20261031-0102-reviewer-c940-pr388-environment-scan.md |
| C-945 | PASS WITH CONDITIONS | 20261030-2348-reviewer-c945-pr391-compose-copy-alone.md |
| C-946 | PASS WITH CONDITIONS | 20261030-2348-reviewer-c946-pr388-missed-shapes.md |
| C-947 | PASS WITH CONDITIONS | 20261030-2350-reviewer-c947-pr384-vs-pr380-new-head.md |
| C-948 | PASS WITH CONDITIONS | 20261030-2351-reviewer-c948-pr383-warning-sites.md |
| C-949 | PASS WITH CONDITIONS | 20261030-2352-reviewer-c949-pr382-soak-override.md |
| C-950 | PASS WITH CONDITIONS | 20261030-2357-reviewer-c950-pr381-vs-318-330.md |
| C-951 | PASS WITH CONDITIONS | 20261030-2358-reviewer-c951-pr387-after-c43.md |
| C-952 | PASS WITH CONDITIONS | 20261030-2358-reviewer-c952-pr385-after-c899.md |
| C-953 | PASS WITH CONDITIONS | 20261030-2358-reviewer-c953-pr369-recheck.md |
| C-954 | PASS WITH CONDITIONS | 20261030-2359-reviewer-c954-pr380-vs-384.md |
| C-955 | PASS | 20261030-2359-reviewer-c955-pr389-batch-bz2.md |
| C-956 | PASS WITH CONDITIONS | 20261031-0000-reviewer-c956-pr351-newest-head.md |
| C-957 | PASS | 20261031-0003-reviewer-c957-pr322-race-delta.md |
| C-959 | PASS | 20261031-0008-reviewer-c959-pr388-after-c913.md |
| C-960 | PASS | 20261031-0008-reviewer-c960-pr322-newest-head.md |
| C-961 | PASS WITH CONDITIONS | 20261031-0010-reviewer-c961-pr325-dead-code.md |
| C-962 | PASS WITH CONDITIONS | 20261031-0011-reviewer-c962-pr355-boundaries.md |
| C-963 | PASS WITH CONDITIONS | 20261031-0013-reviewer-c963-pr360-burst-window.md |
| C-964 | PASS WITH CONDITIONS | 20261031-0014-reviewer-c964-pr340-gateway-enforce-second-read.md |
| C-965 | PASS | 20261031-0015-reviewer-c965-heads-349-352-358-361.md |
| C-966 | PASS WITH CONDITIONS | 20261031-0018-reviewer-c966-pr379-newest-head.md |
| C-967 | PASS WITH CONDITIONS | 20261031-0019-reviewer-c967-pr382-new-head.md |
| C-968 | UNVERIFIED | 20261031-0021-reviewer-c968-merge-readiness-sweep-a.md |
| C-969 | UNVERIFIED | 20261031-0021-reviewer-c969-merge-readiness-sweep-b.md |
| C-970 | PASS WITH CONDITIONS | 20261031-0021-reviewer-c970-pr379-open-conditions.md |
| C-971 | PASS WITH CONDITIONS | 20261031-0021-reviewer-c971-pr369-order-vs-374-375.md |
| C-972 | PASS WITH CONDITIONS | 20261031-0025-reviewer-c972-pr308-vs-pr305.md |
| C-973 | PASS WITH CONDITIONS | 20261031-0026-reviewer-c973-pr317-pr316-gx10-needs.md |
| C-974 | PASS WITH CONDITIONS | 20261031-0028-reviewer-c974-pr297-ci-red.md |
| C-976 | PASS WITH CONDITIONS | 20261031-0030-reviewer-c976-compose-stack-on-new-main.md |
| C-977 | UNVERIFIED | 20261031-0030-reviewer-c977-prs-335-361-vs-new-main.md |
| C-978 | UNVERIFIED | 20261031-0031-reviewer-c978-soak-lines-on-main.md |
| C-979 | PASS WITH CONDITIONS | 20261031-0034-reviewer-c979-pr343-pip-scanner-shapes.md |
| C-980 | PASS WITH CONDITIONS | 20261031-0037-reviewer-c980-pr358-host-spellings.md |
| C-981 | PASS WITH CONDITIONS | 20261031-0038-reviewer-c981-pr384-keep-recommendation.md |
| C-982 | PASS WITH CONDITIONS | 20261031-0038-reviewer-c982-pr381-vs-330-on-new-main.md |
| C-983 | PASS WITH CONDITIONS | 20261031-0039-reviewer-c983-pr374-internal-secret-recheck.md |
| C-984 | PASS WITH CONDITIONS | 20261031-0039-reviewer-c984-pr375-prefix-recheck.md |
| C-985 | PASS WITH CONDITIONS | 20261031-0039-reviewer-c985-pr383-warning-recheck.md |
| C-987 | PASS WITH CONDITIONS | 20261031-0039-reviewer-c987-pr387-pr391-on-new-main.md |
| C-988 | PASS WITH CONDITIONS | 20261031-0041-reviewer-c988-pr355-recheck.md |
| C-989 | PASS WITH CONDITIONS | 20261031-0041-reviewer-c989-pr392-c0-cadence.md |
| C-990 | PASS WITH CONDITIONS | 20261031-0041-reviewer-c990-pr381-recheck.md |
| C-991 | PASS | 20261031-0041-reviewer-c991-pr388-pr325-heads.md |
| C-992 | PASS WITH CONDITIONS | 20261031-0041-reviewer-c992-pr369-moved-head.md |
| C-993 | PASS | 20261031-0041-reviewer-c993-pr322-recheck.md |
| C-994 | UNVERIFIED | 20261031-0051-reviewer-c994-c998-batch-inputs.md |
| C-999 | PASS WITH CONDITIONS | 20261031-0052-reviewer-c999-pr356-rulings.md |
| C-1000 | PASS WITH CONDITIONS | 20261031-0052-reviewer-c1000-pr368-mcp-pr1.md |
| C-1001 | PASS WITH CONDITIONS | 20261031-0052-reviewer-c1001-mcp-write-prs-vs-c902.md |
| C-1002 | PASS WITH CONDITIONS | 20261031-0054-reviewer-c1002-verify-f-c847-1.md |
| C-1006 | PASS WITH CONDITIONS | 20261031-0057-reviewer-c1006-pr379-current-head.md |
| C-1038 | PASS WITH CONDITIONS | 20261031-0200-reviewer-c1038-pr342-delta.md |
| C-1041 | PASS WITH CONDITIONS | 20261031-0145-reviewer-c1041-pr381-delta-9a6aeb3.md |
| C-1050 | PASS WITH CONDITIONS | 20261031-1359-reviewer-c1050-pr363-video-script-delta.md |
| C-1053 | PASS WITH CONDITIONS | 20261031-1743-reviewer-c1053-docs-prs-334-335-378-393-396-398.md |
| C-1055 | PASS WITH CONDITIONS | 20261031-1752-reviewer-c1055-tests-prs-387-388-404-406-407.md |

## B. State changes from PR or main evidence
| Card | Proposed | Evidence |
|---|---|---|
| C-854, C-873, C-892 | DONE | PR 376 (batch BY) merged 2026-10-30T21:29:28Z; reports in table A |
| C-902, C-929 | DONE (C-929 except named items) | builder note 20261110-2100-builder-lane1-mcp-cards-done.md; PR 380 open, head b8af78f |
| C-1033 | OBSOLETE | PR 384 closed unmerged 2026-10-31T01:07:01Z; reports 20261031-1600-builder-lane16-c902-c1033-superseded.md and the Lane 1 note above |
| C-1013 | DONE | 20261101-1900-builder-lane1-c1013.md: F-C943-1 already closed on PR 382 head 0dde283 (open PR head is 0dde283) |
| C-802, C-803 | DONE (check once) | 20261030-2100-builder-lane13-c802-c803-already-on-main.md names the main commits; I did not re-diff main |
| C-821, C-823 | DONE (check once) | 20261108-2330-builder-lane11-c821-c823-already-built.md (title only; not re-verified) |
| C-911 | REVIEW | PR 392 (docs/c0-cadence-five-minutes-c911) is open at 36c0d55; main tasks/todo.md:477 and :624 still read "every 15 minutes", so the work is not on main |
| C-477 | SUPERSEDED or CHECK | PR 293 closed unmerged 2026-10-30T10:29Z; card says fold into C-453, and C-453 is DONE (TASK-QUEUE line 468, main b929f12; follow-ups C-500, C-506, C-512) |
| C-719 | CHECK | PR 324 closed unmerged 2026-10-30T17:12Z; the card asks the PR 324 author to close three findings. I cannot see whether the force-gateway flag fix landed another way |
| C-825 | CHECK | PR 357 closed unmerged 2026-10-30T21:30Z; its commit went into batch BY (PR 376, merged); builder note says part done |
| C-84 | keep OPEN | PR 59 merged 2026-10-28; the card is unblocked work (main test_alerts_ntfy.py:200 still has the shared table), not stale |
| C-733 | keep OPEN | 321 and 324 closed, but 305, 327 and 315 are still open |

## C. Not verified
- Builder-report-answered cards with no PR evidence checked: C-551, C-615, C-673, C-757, C-758, C-804, C-806, C-811, C-1042, C-1059.
- C-744 has a design note (20261104-2300-design-c744-coverage.md) without a verdict word; left out of table A.

## D. Backlog
Added Q-08 to Q-19 to BACKLOG.md: the 12 open PRs whose current head sha7 appears in no reviewer or design report (PRs 336, 344, 347, 359, 362, 363, 373, 377, 393, 407, 408, 409). All read, not measured.
