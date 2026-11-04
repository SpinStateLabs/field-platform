builder-1: B-REBUILD-PR466 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/576 "rebuild of #466", branch rebuild/pr466-sealed-ledger-pair, head 28734cdd1440651a7fed3f28af633e4d72c61122 on origin/main 97dcfec1. Old head c00dc6c9 untouched. Conflict-free, 2 commits, range-diff identical (=). Ran: sealed-ledger 815 passed 5 skipped; env-doc 62 passed; anchors 0 wrong.
NOTE TO COORDINATOR: CI on my rebuild PRs (and 542) fails only on main-red test_http_env_proxy_lint_c57 (tools/start_role_session.py from #532); fixes are #543 / #546, none merged yet. Merge one of those first or every PR stays red. I commented on 542 and 549 once each; other PRs will show the same.
Range-diff:
1:  c62ccd78 = 1:  da7a7f41 sealed-ledger CLI and witness: the operator pair rides only a guarded ledger write (C-1181, C-1150 F2 slice C part 3)
2:  c00dc6c9 = 2:  28734cdd sealed-ledger witness: rename a local variable that the environment-doc scanner reads as os.environ (C-1181)
