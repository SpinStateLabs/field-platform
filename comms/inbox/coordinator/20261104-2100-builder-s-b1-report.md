# Report: S-B1 (scout round 2, file 20261104-2000-builder-scout2-proposals-and-s-a1-report.md), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for the hygiene regex before I started.
PR 492 (draft): https://github.com/SpinStateLabs/field-platform/pull/492, branch fix/hygiene-correction-regex-sb1, head 389eeca6b9d597460c026f7977480e29aba1cc68 (one commit on main cd3b7690, noreply identity). Reviewer needed.
Bug: telemetry.py:24 `that (is|'s) incorrect` needs a space before 's, so "That's incorrect." was never a correction (R: scout probe reproduced by the 4 red tests). Fix: `that(?:\s+is|['’]s)\s+incorrect`. New test_telemetry_analyze.py, 18 tests, one positive and one negative per marker. Failing first (4 red), green. force-gateway suite 466 passed; one mutant (old regex) 4 red.
Not changed: `i don't know` (_SOURCE_HONESTY) and `i'd be happy to` (_FLATTERY) also miss the curly apostrophe; propose as a follow-up card if wanted.
Not run: GX10, other 15 suites.
Open PRs by this builder today: 488 (P-6), 489 (P-1), 490 (S-A1), 492 (S-B1).
