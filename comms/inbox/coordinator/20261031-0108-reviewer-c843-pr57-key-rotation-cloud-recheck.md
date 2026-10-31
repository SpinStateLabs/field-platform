VERDICT: PASS WITH CONDITIONS on 30ac1e11c259656259148e230fbde5ae6facc6c1 (do not arm; merge of the inert code is Don's call)
Card C-843, HIGH CARE. PR 57 at its current head (fetched this session via refs/pull/57/head; equals the card's head). Cloud reviewer, no GX10, no real key or service: every key and secret below is a made-up string in a temp directory, and none is printed. UNVERIFIED until a GX10 re-run. Prior full reviews exist at this same head (Lane 5 C-843, GX10, 70 mutants, 576 crash points; Lane 15 C-894); this is an independent cloud re-check, not a repeat of the crash sweep, which I could not run.

OBJECTIONS FIRST
1. Premise of the card's soak item: there is no 24 h soak change to make in PR 57. `_soak_seconds` is max(identity.soak_s, MIN_SOAK_S = 15 min, 3 x observer tick) (packages/field-core/src/field_core/rotation.py:129-130, 1559-1560). The only 24 h constant is INFLIGHT_LIMIT_S, the abort limit for a rotation that has not reached PROMOTE (rotation.py:136-137). Lane 5 made the same correction; I confirm it by reading the lines. HIGH.
2. A false alarm of my own, retracted: `git log origin/main..p57` in my shallow clone (53 commits) showed 220 commits. That is an artifact of the shallow boundary. The GitHub API says 13 commits, 10 files changed, base ad42410, mergeable state clean. All findings below use the API count.
3. Lane 5's two MEDIUM conditions are still open and I re-proved the second: (a) lost update in `_publish` (no compare-and-swap; not re-probed by me, relied on Lane 5's probe and the unchanged file); (b) the ledger append client keeps the proxy environment and sends the operator key (below). Do not give the rotator a live config until both are closed.
4. Failure conditions: (i) a revocation made during a rotation is silently undone (a); (ii) the rotator's operator key (the NEW key during a `self` rotation) goes to whatever the proxy variables name (b); (iii) a constant changed without a test turning red (F-C843-4 below).
Steelman: the PR adds no scheduler or compose entry, so merging runs nothing; the C-496 blocker is closed for the estate probe client; CI is green on all 7 jobs at this head.

ASSUMPTIONS
A1 Head 30ac1e1 as fetched. A2 CI read through the REST check-runs of that sha (statuses only, run ids not read). A3 Python and tests as installed here; httpx behaviour as in this environment.

REASONING
1. CI at the head: 7 of 7 check-runs success (tests 3.11, 3.12, 3.13, 3.14, compose-smoke, compose-upgrade-smoke, fly-image-smoke). HIGH.
2. Merge: PR 57 vs main exit 0; vs PR 381 exit 0 (git merge-tree). HIGH.
3. Tests at the head: field-core rotation files (r4a, diff guard, review fixes, survivors) 179 passed; tools operator_rotate and keygen files 28 passed. HIGH.
4. Probe, F-C843-2 re-proved: tools/operator_rotate.py:92 builds `LedgerClient(base_url=...)` whose default client does not set trust_env=False (packages/field-core/src/field_core/clients.py, no trust_env at the class; also true on PR 381's version). With the proxy variables pointing at a local listener and a made-up perimeter secret and operator key file: `HttpEstate.append` sent 1 request to the proxy listener and 0 directly, carrying x-field-auth, x-field-operator and x-field-operator-key. The estate GET probes use `httpx.Client(trust_env=False)` (operator_rotate.py:88) and are fine (Lane 5, not re-run). HIGH.
5. Mutants on rotation.py constants, each applied once, tests run `-x`, restored by git checkout (tree clean after): MIN_SOAK_S 15 min to 0 KILLED; SOAK_TICKS 3 to 0 KILLED; ESTATE_SPACING_S 6 h to 0 KILLED; INFLIGHT_LIMIT_S 24 h to infinity KILLED; INCIDENT_EXTRA_S 1 h to 24 h SURVIVED; NOT_BEFORE_SKEW_S 5 min to 0 SURVIVED; KEY_LIFETIME_S 75 d to 750 d SURVIVED; CONFIRM_SWITCH_S 30 to 3000 SURVIVED. 4 of 8 survive. These four constants are used at rotation.py:648, 1454-1455, 1457, 1599, 278; none was named in Lane 5's or Lane 15's reports that I searched. HIGH.
6. Commit identity: of the 13 PR commits, 7 carry the Don Hagell no-reply identity as author and committer; 6 (74ca7398 to 09dcbcd0, the oldest) have blank e-mail fields and a name field that is not Don Hagell's name (the author name field is an address-like string; I do not reproduce it). HIGH (API). The rule says author and committer must be the no-reply identity.

FINDINGS
F-C843-1 (MEDIUM, open, carried from Lane 5): lost update in `_publish`, rotation.py:850-869. Blocks arming.
F-C843-2 (MEDIUM, open, re-proved): ledger append client honours the proxy environment and sends the operator key; fix in `LedgerClient` (also affects PR 381 and every field-core client; my C-876 F-C876-2). Blocks arming.
F-C843-3 (MEDIUM-LOW, open, carried): lost status.json freezes a rotation as foreign_edit (Lane 5).
F-C843-4 (LOW-MEDIUM, NEW): four constants unpinned: KEY_LIFETIME_S (key validity), NOT_BEFORE_SKEW_S, INCIDENT_EXTRA_S (compromised-key expiry), CONFIRM_SWITCH_S. Pin each with a value test. Does not block merge; blocks any claim that the timing is tested.
F-C843-5 (LOW-MEDIUM, NEW): 6 of 13 commits fail the identity rule. Merge-commit would bring them onto main; squash would not. Don's call; a squash avoids it.
F-C843-6 (INFO): the soak item in DECISIONS-FOR-DON is a mix-up (objection 1).

CONDITIONS
C1 (blocks arming) F-C843-1. C2 (blocks arming) F-C843-2. C3 (non-blocking) F-C843-3 and -4. C4 (Don) merge method for F-C843-5; soak item 3 to be withdrawn as a mix-up.

NOT VERIFIED: GX10 16-suite run and the 576-point crash sweep (relied on Lane 5), the lost-update probe, Windows, real estate behaviour, CI run ids and logs.

CONCLUSION
Same head, same verdict as Lane 5 and Lane 15. I reproduced the proxy leak, confirmed the soak premise from the source, and found four unpinned timing constants and six commits that fail the identity rule. Do not arm; merging the inert code does not run anything. UNVERIFIED.
