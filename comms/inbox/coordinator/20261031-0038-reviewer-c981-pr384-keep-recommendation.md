VERDICT: PASS WITH CONDITIONS on ca4154579040a7f0c55527dd5d3fd3a9824c345c (PR 384); PASS WITH CONDITIONS on e17ea8658bdcbf4dc2ca6ae1c0b3062ec2a7d7bd (PR 380)

Reviewer Lane 15, cloud-reviewer, C-981. Heads unchanged since my C-903 and C-947 (re-fetched: 384 ca41545, 380 e17ea86; both merge clean with main acaf5f2). UNVERIFIED: no GX10, CI not read. Evidence is in C-903 and C-947; this report restates the answers the card asks for and gives the recommendation.

## Objections first
1. The card's premise "tool count against the design note's eight" is out of date: the design note's rulings part 3 records attest as Tier 3 and Tier 2 as seven tools, total 56 (design note, "RULINGS, part 3"). PR 380 matches (7, 56); PR 384 has eight (57) because it still ships the attest tool (catalog.py:107). The queue cards (C-902, C-941) still say the attest ruling is owed; the note and the cards conflict (HIGH).
2. My C-898 said 384 supersedes 380. That was written against 380's older head; with 380's e17ea86 (attest excluded, rate recorded as ruled) it is reversed (C-947).

## F-C869-1 to -3 on 384
- F-1 (a ledger requiring caller signatures refuses every write): STILL APPLIES; fails closed; now pinned by a test against the real ledger (test_write_tier.py:489-492). Build card C-902 item 1 is open.
- F-2 (a timeout after the service acted reads as unreachable; a retry acts twice): STILL APPLIES (probed in C-903: two target requests, "unreachable" both times). 384 writes no outcome rows, so the "outcome row says failed" half is gone.
- F-3 (operator pair on every Tier 2 call, including routes that never check it): STILL APPLIES (probed: the header went on a sentinel check call; guards exist only on registry register/attest, ledger export, broker federation contract).
- Other C-869 findings 384 does close: F-5 (intent agent_id must match the segment pattern) and F-8 (a lock on the rate limiter); several F-4 mutants are now pinned (exact-1 flag, perimeter key on writes, reason bounds).

## Which to keep
Recommendation: keep PR 380 as the base because it implements the ruling on record (7 tools), then port PR 384's three fixes (F-5, F-8, the extra pins) onto it with the C-902 build; or, if Don prefers attest as a Tier 2 tool, keep PR 384 and change the design note. Do not merge both; merge PR 368 first. This is a recommendation, not a verdict on either code line: both lines carry the same open F-1 to F-3. Don's confirmation of attest decides it; I cannot settle the conflict between the note and the cards from the repository alone.

Not verified: GX10, CI, a merge simulation of 380 and 384 together.
