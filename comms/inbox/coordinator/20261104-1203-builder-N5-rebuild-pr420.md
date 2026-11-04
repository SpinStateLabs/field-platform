# Builder builder-N5: B-REBUILD-PR420

PR 567 (draft, "rebuild of #420"), branch rebuild/pr420-renew-token-pins, head b899ec631422a0751c24cfdc00bd56ac325d5de1, base main 97dcfec1. Old PR 420 head e01094d187b08c94ef833da415596a816cd02b7f, untouched. UNVERIFIED: no GX10, CI just started.

Range-diff: 3 of 3 commits "=" (cherry-picks clean, no conflicts, only main drift). Note: tools/renew_token.py changed on main since the old base 4d0c3315 (+22/-5), so the old GX10 16/16 was on different code: fresh GX10 run needed.

Ran: new file 16 passed (needs field_core installed; skips otherwise); mutant os.path.isdir negated in tools/renew_token.py -> 2 failed, restored; with c57 + environment_doc tests 179 pass, 1 fail = known c57 allowlist baseline (PR 543); environment_anchors --check 0 wrong.
Not verified: GX10, CI, full tools suite.
Decisions needed: none; coordinator to close PR 420 after review (I did not).
