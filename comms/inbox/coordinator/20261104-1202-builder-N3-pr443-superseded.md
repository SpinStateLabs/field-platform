# Builder B-REBUILD-PR443: not rebuilt, PR 443 is superseded by merged main

Result: no branch, no PR. UNVERIFIED (no GX10). Old head 98fc9151 (4 commits: ed8b68b1, be07987e, 55e2d43c, 98fc9151).

Claim check on current main: commit 2349eeb5 ("agent-registry and federation-broker: a 422 no longer repeats a caller-chosen key name; the guard finds a real call by ast (C-1128, reviewer C-1123 F1 and F2)") is already on origin/main. It does the same job as commits 2-4 of PR 443 by a different route:
- agent-registry installs install_validation_handler, REDACTED_NAME in loc (PR 443: same, literal "(field)").
- federation-broker keeps its handler and redacts loc names with _known_names/REDACTED_NAME inline (PR 443: via a new redacted_loc helper in field_core/http_errors.py).
- the guard test scans for a Call node by ast (PR 443: same idea, different code).
Main also has C-1158 (Don's ruling on C-1123 F3) tests in tools/tests/test_422_handler_installed_c1114.py that PR 443's last commit conflicts with in 3 hunks.

What I ran: cherry-picked the 4 commits onto origin/main in order. Commit 1 (redacted_loc helper + its test) applied cleanly. Commits 2, 3, 4 conflicted in api.py (federation-broker, agent-registry), test_d3_scan_hardening.py and test_422_handler_installed_c1114.py; every conflict resolved toward main's equivalent text, which would leave a near-empty diff. I aborted and deleted the local branch; nothing pushed. range-diff not produced (no rebuilt branch).

Decision needed: close PR 443 as superseded by 2349eeb5 (coordinator's call; I did not touch it). Only unmerged piece is the field_core redacted_loc helper (+69-line test); if wanted, it is a separate small card, and nothing on main calls it. Lock released.
