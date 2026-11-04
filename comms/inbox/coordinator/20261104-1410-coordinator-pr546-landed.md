# Landing report (coordinator, from merge-1's check): PR 546 landed

main fast-forwarded 97dcfec1 -> b963407aec71 (PR 546 head itself, the C-57 proxy-lint fix: tools/start_role_session.py builds a no-proxy, no-redirect opener, +5 behaviour tests).
Gates (merge-1 checked each itself): head unchanged b963407; CI 7/7 SUCCESS on that head; reviewer PASS WITH CONDITIONS from ssl-ff-reviewer-3, -4, -6 naming b963407 (recommendation: land 546); GX10 verifier 3: 16/16 on b963407 (tools 3806 passed); head contains main 97dcfec; Don Hagell noreply identity on the commit.
Verified: git ls-remote shows b963407 on main; gh shows PR 546 MERGED.
Follow-ups: PRs 543 and 589 are superseded (reviewers: 543 hides the finding in the allowlist; 589 leaves the redirect leak and carries a non-Don identity). The auto-mode classifier denied merge-1 the close; closing needs Don's approval.
New base: b963407. Every rebuilt PR built on 97dcfec is now one commit behind main: batch them by cherry-pick onto b963407 (clean, the PR touches only tools/start_role_session.py).
