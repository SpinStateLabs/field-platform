# B-COND-PR821-7401a69: condition 1 met by a NEW PR 850 (PR 821 head untouched); condition 2 open

New PR https://github.com/SpinStateLabs/field-platform/pull/850, head 889e05cbdd72, branch rebuild/pr371-manifest-containment-clean.
- Tree identical to 7401a693 (`git diff` empty). 17 commits, the eight Fable trailers removed (0 left; the seven Sonnet 5.5 trailers kept), author and committer Don Hagell on all 17, nothing under .github.
- I did not force-push 821: its verdict is PASS WITH CONDITIONS and a re-cut rewrites 17 commits. Coordinator closes 821 once 850 passes re-review (reviewer-7's verdict on 821 covers the same tree).
- Condition 2 (CI green and 16/16 GX10 on the exact head) is open: needs CI and a verifier card on 889e05c. The 3 Windows-only field-core failures reviewer-7 saw are unchanged and unverified on Linux.
- LOW follow-ups for B-FU-PR821-*: portable mtime test (write_bytes), clamp the echoed manifest_ref, reviewer-4's open survivors.
