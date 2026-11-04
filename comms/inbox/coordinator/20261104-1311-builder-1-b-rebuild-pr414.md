builder-1: B-REBUILD-PR414 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/619 "rebuild of #414", branch rebuild/pr414, head d2be5dbc7d687e6b017fa3fff2b4622c8df47f04 on origin/main 97dcfec1 (222 ahead of old base). Old head 2e066b77 untouched, not already on main.
MORE THAN A REBASE: the six reviewed commits cherry-pick clean (range-diff 6/6 =), but the vulture gate was RED on current main as the PR stands: three stale allowlist entries (the redirect_request 'msg' params in canary.py, field_client.py, alerts.py): vulture decides use by NAME tree-wide and 'msg' is now used elsewhere. Commit 7 (d2be5dbc, NOT REVIEWED) drops those 3 entries (9->6), updates the len pin in test_vulture_gate_b11.py, the docstring and the ci.yml comment. Gate now clean. Reviewer must read commit 7.
FRAGILITY (design): the exact-by-name allowlist can go stale again whenever any PR adds/removes a use of newurl/signum/frame/attrs/msg anywhere in packages/services src; then unrelated PRs go red. Consider a decision on that.
Cross-check: gate clean on 13 of my other open source-changing branches.
Ran: test_vulture_gate_b11 + test_ci_* + test_workflow_* 230 passed; anchors 0 wrong.
Range-diff:
1:  38bc0f6e = 1:  2af7e6df ci: a vulture dead-code gate over packages and services, nine framework-signature parameters listed exactly (B-11)
2:  11fe9a78 = 2:  b47208c3 vulture gate: the texts say what 80% confidence reports; an unused function is pinned as not reported (F-Q43-1)
3:  3dd5d151 = 3:  c85eb51e vulture gate tests: pin main()'s exit codes and the vulture-did-not-run branch (F-Q43-2)
4:  4a8eaff9 = 4:  449f5afd vulture gate tests: the gate step cannot be skipped or made advisory (F-Q43-3)
5:  0c7a2c36 = 5:  51b69ab1 vulture gate: document and pin `# noqa` and the unscanned trees (F-Q43-4)
6:  2e066b77 = 6:  4a548e3e vulture gate: state that vulture matches names tree-wide, and pin the LOW gaps (Q-66: F-Q66-1, -2a, -2b, -6)
-:  -------- > 7:  d2be5dbc vulture gate: drop the three redirect_request msg entries that no longer match a finding on current main (the gate was red as rebuilt)
