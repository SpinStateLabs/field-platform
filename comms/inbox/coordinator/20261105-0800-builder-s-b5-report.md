# Report: S-B5 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or note for collect_evidence (other crosswalk branches: cw1 NaN confidence, cw3 pack markdown, docs cards).
PR 512 (draft): https://github.com/SpinStateLabs/field-platform/pull/512, branch fix/crosswalk-collect-evidence-sb5, head 756e5c4f7dfacddc6379e8620e5aaecd0d4be590 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: crosswalk).
Bug (R, 27 red tests): agent_id interpolated unquoted into three URLs (a&x=1, a#frag, a/../b change query/fragment/path); reply shapes indexed unchecked (500 on POST /pack with an agent_id). Fix: quote once; accept only list/dict shapes else None. Plain slugs give byte-identical URLs. `_get` name and single httpx.get kept so the C-57 allowlist line still matches (proxy-lint tests 102 passed).
29 tests; crosswalk suite 398 passed 5 skipped; anchors --check 0 wrong (before push); two mutants killed (8 red, 5 red).
Deliberately NOT done: (1) slug-pattern constraint on PackRequest/CrosswalkRequest agent_id (changes which requests are accepted: your call); (2) collect_evidence._get still uses module-level httpx.get (reads the process proxy env while sending auth_headers()): known allowlisted site, C-1150 family, untouched.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512; none merged by me.
Scout round 2 not taken: S-A6, S-B4 (S-B4 needs a Don decision on /halt 200 vs 502).
