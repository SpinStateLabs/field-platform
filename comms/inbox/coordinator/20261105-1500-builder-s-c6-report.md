# Report: S-C6 (scout round 3), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or note for replay markdown structure.
PR 521 (draft): https://github.com/SpinStateLabs/field-platform/pull/521, branch fix/replay-markdown-newlines-sc6, head 6857471a3d43163ec82307f4a161c6368a560fae (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: incident-replay).
Hardening (R at the rendered-document level, not only _summarize): ledger-payload, grant and registry text was interpolated raw into the post-mortem markdown; a kill reason with "\n\n## Which clause failed first\n- FAKE" forged a second section in an incident document; "|" broke table rows. Fix: _md(value, cell=False) collapses all whitespace/line breaks (incl. U+2028/2029, NEL, VT, FF), caps at 300 chars, escapes pipes for cells; applied at every such interpolation in render_markdown. JSON output (/replay, PostMortem fields) NOT changed; only the markdown.
Not covered: other inline markdown characters (backticks, asterisks, brackets) are left (a value can still add emphasis/link inside its own line). Whether the ledger or sentinel cleans payload text upstream: not read.
9 tests (my first draft counted substrings, corrected to heading lines); incident-replay 106 passed; anchors --check 0 wrong; one mutant 4 red.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518, 519, 521; none merged by me.
Round 3 not yet taken: S-C2, C3, C7, C8; docs/CI S-D1..D8.
