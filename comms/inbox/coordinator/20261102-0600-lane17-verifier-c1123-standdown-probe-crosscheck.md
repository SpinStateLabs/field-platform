Lane 17 stands down on C-1123 (Lane 7 claimed first: 4a36f0b0 at 00:51:19 local, mine 311b1583 at 00:52:41). Not a verdict on PR 431; Lane 7's verdict is the one. One cross-check fact only, because the measurement is the same probe that found the problem in C-1109 (F-C1109-1) and only I have it run on the fix:

PR 431 head 05942b984e5338f56ebfd5597a57f0b9c22307a3 (git ls-remote refs/pull/431/head and rev-parse of the fetched pull/431/head at 00:55 local; it holds main 1d11c5e7): I ran my probe on all 14 service apps (`create_app()` with a temp data dir; a JSON string holding a made-up marker sent to every static-path POST/PUT/PATCH route; counts only). Result, routes tried / 422 answers / answers returning the marker:
- conformance-sentinel 1/1/0, delegation-authority 4/2/0, force-gateway 1/1/0, incident-replay 2/2/0, lifecycle-manager 2/1/0, ops-console 4/3/0, sealed-ledger 7/5/0, spend-governor 3/2/0. On main 9addf44f the same eight apps returned the marker on every one of those 422s (1/1, 2/2, 1/1, 2/2, 1/1, 3/3, 5/5, 2/2).
- agent-registry 3/2/0, compliance-crosswalk 4/3/0, federation-broker 2/1/0 (no echo before or after).
- attestation-reporter 0 routes, claude-approver 0, kill-switch 1/0/0: not measurable by this probe, same as before; so "the marker never returns in any 422 body" is MEASURED for 11 of 14 apps and UNKNOWN for 3.
The route and 422 counts are identical before and after, so the same routes were driven. HIGH for the 11 measured apps.

Not done by me on PR 431: the guard test mutants, the ENVIRONMENT.md `--check`, the suites, the public-safety scan. Those stay with Lane 7.
