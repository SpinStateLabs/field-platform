# A-RT3 proposal + DON'S DECISIONS (recorded 2026-11-07) (ssl-fp-architect, 2026-11-07): bound go-sentence form, per-gate freshness and withdrawal, with RT-832-R1/R2
Sources (HIGH, read): reviewer-8 R-RT-HARD-3 report 20261106-2126 (F-H3-3, F-H3-4); origin/main tools/stage_controller.py (`preconditions`, `Records.alerts_proven`, `gate_ok`, `stage_clean`, `_go_fields`, MAX_GO_SENTENCE 500); PR 840 state OPEN (so R1 and R2 are NOT on main); WORKLIST row B-RT3-g24-ack-rollback-and-exclusive-lock already carries F-H3-1 and F-H3-2.

## Objections to any fix here (first)
1. No form of words makes the controller know Don typed it. A caller that can pass a string can pass the well-formed string. A bound form removes accidents (wrong stage, wrong build, stale paste, "go"), not forgery by the caller.
2. The records file is trusted by file permission (stated in the module). Freshness reads `ts`, which the writer chose; anyone who can write the file can write a fresh row. Freshness closes stale and regressed state, not tampering.
3. Short freshness windows add false aborts: a Stage 3 attempt a day late is refused and the deployer must re-prove alerts. That is the intended cost; too short a window trains people to re-record without looking.
4. A strict form is brittle: a typo refuses a legitimate go. Cheap and visible (exit 2, reason named), no estate change.

## Decision 1: go-sentence form (F-H3-3)
Options: (A) fixed token `GO STAGE <n> <sha8>`; (B) A plus a signature by a key only Don holds; (C) status quo.
Recommendation: A now. The controller gets Don's prose as before for the audit hash, and the driver passes one extra token line.
- Form, exact, `fullmatch`, upper-case literals, single spaces, no other text, no newline: `GO STAGE <n> <sha8>` where n is the stage being run and sha8 is the first 8 hex of the build sha the run was given (`sha8_of(build_sha)`). Refuse reasons: `go_sentence_form`, `go_sentence_stage_mismatch`, `go_sentence_sha_mismatch`.
- The sha comes from the build sha the run is bound to, which RT-832-R1 makes mandatory live (below), so a go typed for yesterday's build cannot start today's.
- The records keep `go_sentence_len` and `go_sentence_sha8` as now (the token, not Don's prose).
- Not chosen: B. It is the only option that stops a forging caller, but it needs a new secret, a signing step Don runs by hand, and key storage rules; that is a feature and posture decision. **DON-ONLY: whether Stage 2/3 go sentences must be signed. Until Don says so, A stands and the runbook states honestly that the go sentence is an input the coordinator relays.**
- Rejected: C (the review shows "go" and "." pass); length or word-count rules (cosmetic).

## Decision 2: freshness and withdrawal (F-H3-4)
Two classes of record:
- Code-fact gates, bound to a sha: `gate G21`, `gate G22`. A row for sha8 stays true while the build is that sha; no expiry, because the sha already fixes what was proven. Once RT-832-R1 forces the sha, a back-dated unbound row no longer counts.
- Estate-fact records, which can regress: `alerts_proven`, `gate G18`, the Stage 2 window gate (card B-S3-1), `stage_done` read by `needs_clean_stage`. Each expires: alerts_proven 24 h, G18 and the Stage 2 window gate 72 h, stage_done 7 days, measured from the row `ts` to the moment of `run`. These are architect defaults under the delegation; Don may tighten them and **DON-ONLY: the minimum Stage 2 soak length before Stage 3 (already his, G26) and any longer maximum age.**
- Withdrawal: last row per key wins, key = (kind, gate, sha8). `record withdraw alerts-proven | gate Gn [--build-sha S]` appends an `ok: false` row; a later `ok: true` row re-establishes it. `stage_clean` already works this way.
- A row whose `ts` is missing, unparseable or more than 5 minutes in the future is ignored (counts as absent) and reported once in the plan output as `ignored_rows: n`.
- The plan output prints, per gate, the age of the row it relied on.
- Not claimed: tamper resistance. A hash chain was rejected because whoever can write the file can recompute it; the module's trust statement stays and the runbook repeats it.

## Decision 3: RT-832-R1 and R2 together with this
PR 840 (open, PASS WITH CONDITIONS, card B-PR840-pin-services-rt832) already makes a live run refuse without a build sha (R1) and defaults the expected services per stage (R2). Decision: accept 840 as the R1/R2 fix, no second mechanism. This design builds on it, so order matters:
1. B-PR840-pin-services-rt832 merges (conditions fixed).
2. B-RT3-g24-ack-rollback-and-exclusive-lock (F-H3-1/2, exists).
3. B-RT3-go-sentence-form (new).
4. B-RT3-record-freshness-withdraw (new).
Same file, same tests: one builder at a time, each rebased on the previous. B-S2-2-controller-driver-args (plan flags) lands after 840 and before 3, and the form check there is the same one: its `--go-sentence` requires `--build-sha`.

## What stays Don-only
- Whether go sentences must be signed (Decision 1, option B).
- The Stage 2 to Stage 3 soak minimum and any change to the maximum ages (Decision 2).
- Every go sentence itself (G25, G26). Nothing here arms, installs a key or touches an estate.

## Risk
- Operators must now type `GO STAGE 2 <sha8>` correctly; the deployer's draft Stage 2 sentence in the estate-deployer report gets one line added by the coordinator at the go point.
- 72 h and 24 h expiry can refuse a Stage 2 run when the window was judged earlier: re-record (re-judge) rather than widen.
- MEDIUM: ages are my defaults, not measured from any estate run.

## DON'S DECISIONS (his chat answers, recorded by the coordinator in comms/inbox/coordinator/20261107-0010-coordinator-don-answers-signing-soak-ages-stage2-go.md)
1. Signed go sentence: NOT NOW. The plain token `GO STAGE <n> <sha8>` bound to the run's build sha stands. Signing is a future feature, not built.
2. Soak minimum: 1 h per stage on both estates (auto-rollback on any dropped_unauthenticated or dropped_refused rise).
3. Record ages ACCEPTED as proposed: alerts_proven 24 h, G18 and Stage 2 window gate 72 h, stage_done 7 days; sha-bound G21 and G22 rows never expire. (Don's confidence note: LOW, defaults not from a source.)
The "DON-ONLY" marks above are therefore answered; they are no longer open.

## Order, checked 2026-11-07 against GitHub (HIGH)
PR 840 (B-PR840-pin-services-rt832, head 394d09a, reviewed) is OPEN and is first. Then PR 859 (B-RT3-g24-ack-rollback-and-exclusive-lock, open), then PR 855 (B-S2-2-controller-driver-args, open), then B-RT3-go-sentence-form, then B-RT3-record-freshness-withdraw. None of 840, 855, 859 is on main yet; every card after 840 rebases on the one before.
