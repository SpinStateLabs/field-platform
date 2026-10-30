VERDICT: PASS WITH CONDITIONS on 57a356b38ffc8c6aeabe4e4e020c4f691d25300e  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-887, PR 369 (per-tier perimeter keys) at its newest head, after builder Lane 12's C-795 update. Two commits since my C-859 head (50ba99e): 72892cc (tests, red first) and 57a356b (the fix, authn.py +4 -3): "the two internal operator routes are never in the read tier (C-859 C1)". Conditions are those of C-783 (Lane 4), C-795 (Lane 14) and my own C-782 and C-859. This SHA only.

OBJECTIONS FIRST
1. My C-859 C1 (a read key reaches GET /operator/rotation-state when the internal secret is unset) is CLOSED. authn.py now defines INTERNAL_PATHS = {/operator/verify-hash, /operator/rotation-state} and `install` always unions them into the write-only set. Probe through the real agent-registry app with a fixture operator registry, a full key and a read key (synthetic values): rotation-state with the full key 200; with the read key 401 (was 200); a trailing slash, an encoded hyphen, a dot segment (`/operator/./rotation-state`), a parent segment (`/x/../operator/rotation-state`), OPTIONS and HEAD with the read key all 401; POST verify-hash and GET verify-hash with the read key 401; `/health` without a key 200; an ordinary read route (GET /agents) with the read key 200. A doubled leading slash and a `;x=1` suffix answer 404 (the framework does not route them; a proxy that collapses slashes would deliver the clean path, which is refused). Confidence HIGH (observed). The mutants: removing the union KILLED; removing rotation-state from the set KILLED; removing verify-hash SURVIVES (equivalent: that route is POST only and POST is already non-safe).
2. C-783 conditions at this head: F-C783-1 (write-only list fails open behind a root_path prefix) CLOSED (as C-795 found; the matcher tries the request path and the ASGI path, each with the prefix stripped); F-C783-2 (exact strings only) CLOSED (templates, trailing slash, `{p:path}` and mid-literal templates); F-C783-4 (pin gaps) CLOSED apart from the items below; F-C783-3 (one generic key opens every service's reads) OPEN by design: all 14 services still call `install_authn(app)` with no `service=` and no `write_only_paths` (grep of services/*/src: 14 callers, no hit for `service=` or `write_only_paths`). So no service is on a per-tier setup and a generic FIELD_READ_KEY set in a shared environment opens reads of every service at once, including token records, the ledger chain and attestation packs (C-795 F-C795-4, carried, Don's call). Confidence HIGH.
3. C-795 conditions: F-C795-1 (the `{x:path}` branch unpinned) CLOSED: replacing the multi-segment branch with the one-segment one now turns the suite red (1 failed, 24 passed); F-C795-2 (template literals not escaped, unpinned) CLOSED: dropping `re.escape` now turns it red; the trailing-slash normalisation mutant is red. F-C795-3 (the open-path membership uses request.url.path only; unpinned) not re-probed, LOW.
4. "Any service still on a single key": yes, all 14 services, in the sense of item 2: they use the generic variables and have no per-service read key and no write-only list. This is infrastructure; the answer changes only when an adopter PR passes `service=` and the state-changing GET routes (if any; I did not enumerate them) per service. HIGH on the count; MEDIUM on "if any".
5. The fix hard-codes the two internal paths in field-core, so an operator-health route added later would need adding there too; no test ties INTERNAL_PATHS to the routes operator_health registers (operator_health.VERIFY_HASH_PATH and ROTATION_STATE_PATH exist as constants). LOW: tie them by import or by a test.
6. Combined with PR 374 (C-859): the read key is now refused at the perimeter on both routes whether or not the internal secret is set; PR 374's header still adds a second gate for the full key. No conflict (earlier merge-tree clean; docs/ENVIRONMENT.md only).

ASSUMPTIONS
A1 Card scope: which C-783 conditions are closed; any service still on a single key. A2 The agent-registry app wiring represents the other services (all call the same install helper and operator_health install).

REASONING / CHECKS
- Tests: test_authn_tiers_c772.py 29 passed; whole field-core suite 1161 passed, 1 skipped.
- Mutants on authn.py (each restored, nothing committed): 8 applied: union removed KILLED; rotation-state removed KILLED; verify-hash removed SURVIVED (equivalent); multi-segment template branch KILLED; re.escape removed KILLED; trailing-slash normalisation removed KILLED; safe-method test removed KILLED; write-only check removed KILLED. One further mutant did not apply (text appears twice).
- Commits: author and committer Don Hagell no-reply on every commit. Diff scan: no key material (labelled placeholders), address, flag value or deploy status.

CONDITIONS
C1 (non-blocking) Tie INTERNAL_PATHS to operator_health's route constants (import or a test).
C2 (carried, Don's call) F-C783-3 / F-C795-4: adoption must pass `service=` and list state-changing GETs; decide the attestation pack and token and chain reads before any read key is issued.
C3 (non-blocking) Pin the open-path membership spelling (F-C795-3).

NOT VERIFIED
GX10 full set, CI by run id, the other 13 services' routes one by one at this head, whether any state-changing GET exists.

CONCLUSION
The read key can no longer reach the two internal operator routes, with or without PR 374; the earlier pin gaps are closed. The one-generic-key exposure across 14 services stands until an adopter passes `service=`. PASS WITH CONDITIONS, none blocking for this PR. UNVERIFIED.
