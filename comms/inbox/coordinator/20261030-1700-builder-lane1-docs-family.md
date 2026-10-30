# Builder Lane 1 (docs-vs-code fork): C-545, C-549, C-559, C-571, C-577, C-550 as six draft PRs

All docs-only except C-550's two docstrings; none verified on the GX10 (no GX10 tool), CI not read. Every figure was recomputed from the code on current main; no deploy status, estate value, credential or build SHA in any text. Each note carries the container date 2026-10-30 (change if the project clock differs). Reviewer cards wanted for each; light run for the docs, the force-gateway suite for C-550's comments.

| Card | PR | Head | File | Run |
|---|---|---|---|---|
| C-545 | 334 | 8bea8c4ecd7976e2660e236ae1e9471ccfae613e | ADR Pack 02 (dated note, +8) | env doc test 43 passed |
| C-549 | 335 | 9192e30d18ee3a464053413624906f0f034a73e6 | ADR Pack 07 (dated note, +6; counts 13 controls, 52 entries: 16 cited, 23 pending-text, 13 pending-purchase, recomputed by running the printed command) | env doc test |
| C-559 | 337 | 99888f851930c68fee4a13995e16f6279fbcaa2a | docs/ARCHITECTURE.md (fourteen services, added arrows with file:line, gateway events, enforce-mode perimeter row, demo-figure labels) | env doc test; Mermaid NOT rendered |
| C-571 | 338 | 8cc7e4113137822d0e4d2a4ba66986297b0b288b | docs/IMPLEMENTATION.md (+ one comment line in tools/topology_lint.py: cited line 79 became 84) | env doc + topology_lint tests 330 passed |
| C-577 | 340 | 1643d20a1fe304750d3cc67e90d83d4d66ac3687 | docs/INTEGRATION.md (estate deploy-state sentences removed; enforce-mode headers and 401/403/503 added; mode refusal sentence; demo timing dropped) | env doc test |
| C-550 | 341 | cde33034d50e4d99bce149af99832fb9999bf4fd | ADR Pack 10 note (+8) and two docstrings in force-gateway api.py (net 0 lines) | force-gateway 443 passed; env doc test |

Corrections to reviewer reports found while re-deriving: C-529 said no tenant isolation tests exist in the sentinel; two per-agent isolation tests exist (test_self_manifest.py:93, :123), the note says so. C-534 implied ops-console writes no ledger events; it writes `operator.refused` (ops-console api.py:377-398). The capstone drill figure (~53 ms) in ARCHITECTURE.md differs from the recorded run (43.6 ms kill, 56.3 ms total, field-agent-run.log:33); left as is and labelled, source unknown. The C-530 `InvalidSigner` line reference did not match the code and is not cited.

DECISIONS FOR DON (none taken): (1) C-550: wire owner notification for gateway bypass (a feature) or keep "ledger record only" (done in the comments). (2) C-577/C-571: the two guides disagreed on the demo timing (~30 s vs ~23 s); I dropped one and left the other, neither was measured.
Overlap notes: C-560, C-551 and C-581 (public-safety) touch the same personal-path lines as C-571's two path replacements; the other fork (C-560) may have changed them too, so whichever merges second rebases.
Not done: nothing of the six is open. Blockers: none.
