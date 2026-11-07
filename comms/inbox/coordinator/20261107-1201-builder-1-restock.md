builder-1 restock note, 2026-11-07 ~12:02Z. `dispatch.sh next builder builder-1` returns EMPTY. No fallback builds made.

Done this stretch (each a NEW draft PR from current main, the old PR not pushed to; all need a reviewer row on the new head):
 868 (PR 829), 869 (805), 870 (798), 871 (758), 872 (752), 873 (750), 874 (748), 875 (746), 876 (745), 877 (742), 878 (734), 879 (730), 880 (728), 881 (727), 882 (723), 883 (722), 884 (720), 885 (715), 886 (712), 887 (709), 888 (696), 889 (695), 890 (694), 891 (690), 892 (688), 893 (686), 894 (684), 895 (679), 896 (676).
Each PR body lists the checks run, the mutants (and any that survived, with why), and its Decision for Don. Reports are in comms/inbox/coordinator/ (slugs conf829 ... conf676).

Held claims, NOT built, waiting on Don or the architect:
 - B-COND-PR606-c3af479: only open conditions are C1 (a decision for Don: copy upstream text into verdict reasons or fixed texts), a LOW follow-up, and a CI gate; and no ruling on pushing to existing PR branches.
 - B-COND-PR866-293075c: only open condition is C1, PR 866 vs PR 495 (policy). Measured: PR 495 conflicts in force_gateway/api.py with draft PR 884.
 - B-CONF-PR450-483e3f4: the old Phase E words work; add/add conflict with the ruled E1 v2-one-liners.md; options A (close as superseded), B (port non-conflicting wording only), C (also port e_gate.py). See conf450-hold.
Still open questions for Don are in the PR bodies; the main ones: 870 (exit 2 vs exit 3 for wrong shapes), 875 (NUL --anchors order and path echo), 895 (n8n loader error wording), 890 (name rule copy), 886 and 893 (unreachable validators), 868 and 878 (allowlist rows).

One CI note: PR 879's tests (3.12) failed once on an unrelated renew-token canary test; re-run attempt 2 passed that step; one comment posted on 879.

Next: re-check in 60 minutes. If cards appear I take them; I will not push to an old PR head without a ruling.
