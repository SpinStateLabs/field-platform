# Builder builder-N5: B-S5-24

PR 701 (draft), branch test/deployment-manifest-test-injected-clock-s5-24, head 2c1be31c8194fa66dda19a4fb4fd1147eb164df0, base main b963407a. UNVERIFIED: no GX10, CI just started.

Scout evidence re-checked on main, HIGH: the test used now=None, manifest delegation.expiry placeholder 2026-11-22, field_core adds 'the delegation has lapsed' from that day. Tests only; manifests/deployment-agent.yaml untouched.

Change: clock injected at manifest expiry minus 10 days, read from the manifest (deviation from the card's fixed date: survives Don moving the placeholder); near-term window asserted; second test pins exactly one new 'lapsed' warning for a clock past expiry.

Ran: file 26 passed 1 skipped (unrelated delegation_authority import skip); with c57/c505/environment_doc/anchors 287 passed 1 skipped; environment_anchors clean. Mutants in field_core validation.py (wording changed; lapsed test weakened) both red, restored.
Not verified: GX10, CI, a run under a faked real clock after 2026-11-22.
Decisions needed: none. Reviewer other than the author. Related: scout S-D8 (topology allowlist 2026-11-23) is the same family, not touched.
