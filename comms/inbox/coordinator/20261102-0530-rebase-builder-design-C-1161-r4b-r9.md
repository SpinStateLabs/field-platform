# C-1161: design note, key rotation R4b and R9 (Lane R). DESIGN ONLY: no code, no PR, no GX10 run. Made-up keys only; no estate value.

Read: rotation.py, rotation_events.py and tools/operator_rotate.py as on my rebuild rebase/57-c1156 (648a933e; the 10 PR 57 files are byte-identical to PR 57's head 30ac1e11, so the line numbers below are the same on PR 57); alerts.py; the comms notes named in each section. NOT in this repository: the "key rotation design v0.2" document the code cites (sections 4, 5.1, 8). I do not know its slice list beyond what the code comments and review notes quote, so every statement about R4b and R9 below rests on those quotes. Nothing was run for this note.

## OBJECTIONS (first)
1. The sources disagree on line numbers because they read different PR 57 heads (C-29 cites `_locked` at 1086-1089 and the cap at 157; on 30ac1e11 they are 1078-1100 and 160). Numbers here are from the rebuild; re-check at the head you build on.
2. "R9" is one name for two different things: an AUTOMATIC reconcile (C-29's proposal) and five OPERATOR COMMANDS (`--abort-inflight`, `--reconcile`, `--extend`, `--downgrade-format`, `--accept-roster`) plus a recovery mode. The slice list does not say which the design means by R9, so I split it and say so; the coordinator may merge them back.
3. Order risk: R9's automatic restore writes key files, the most dangerous code in the rotator, and the first place it can meet real services is R4b. Doing R9 first means testing it only against fakes.
4. This note lists decisions that are already open (D-5, D-6, soak length) for Don; it does not answer them.

## ASSUMPTIONS
A1 (HIGH, read): the rotation.py header says "Not in this slice (design section 8)": the five operator commands and recovery mode (R9), the compose e2e (R4b), typed spool requests in diff_guard (H2, B1), and the job's own lock (R5; job identities must not go into a live rotator config before it).
A2 (HIGH, read): D-6 is "keep halting (fail closed) until an R9 reconcile exists" (Don, 2026-11-05, groomer-don-rulings-2). D-5 (the post-PROMOTE retry cap) is provisional.
A3 (MEDIUM): C-843 (Lane 5) says merging PR 57 is inert and ARMING must wait for F-C843-1 (compare-and-swap: a revoked operator can come back) and F-C843-2 (the ledger client sends the rotator's key through a proxy), and that F-C843-3 to -6 should land before or with R4b.

## WHAT EACH IS
**R4b = the compose end-to-end.** Run the real rotator, `tools/operator_rotate.py`, against the eight operator-block services started by compose, with made-up keys and a short soak, and check what only a real service can show.
- Inputs: a compose profile with the eight services, each serving `/operator/rotation-state` and `/operator/verify-hash` and reading one shared made-up operators file; a made-up format-2 operators file and key files in a volume (mode 0600); the rotator's config (settings, the eight service URLs, the ledger URL, identities with a short `soak_s`); an injectable clock only where the rotator takes one.
- Outputs (the assertions): one identity rotated end to end through PREFLIGHT..CLEANUP; every service answers `current` for the new key (9b) and `none` for the old hash (10 CONFIRM-REFUSED); the ledger holds the events in order with only 16-hex fingerprints; no key bytes in any log or event; the old key file removed only after both checks.
- Failure modes only a real estate shows: a service that reloads the file late (VERIFY-NEXT timing); a service reporting a generation above the file's (the rotator's `max(live, services, high-water) + 1` rule); proxy variables in the container (`trust_env=False` is pinned by the C-57 lint, but not exercised end to end); uid and mode mismatches between host and container (C-843 F-C843-5, -6: LOW confidence, depends on uids); a kill of the rotator mid-SOAK and the resume; the Windows lock branch (not covered by Linux compose; C-843 did not test it).

**R9 = recovery.** Two parts.
- R9-auto (C-29's design, Lane 13, 20261030-1522): per halted identity read the live row's current and next hashes, the key file, `.prev`, the journal phase and what every service says for each hash, and act only on proof: (a) live == sha256(`.prev`) and every service agrees: restore and drop `next_key` (this abort path already exists); (b) live == the new key everywhere: go forward (exists); (c) a foreign edit that is key-slot-only or roster-only: accept; (d) anything else: HALT, park that identity, alert.
- R9-commands: the five operator commands above, for a person to clear a state the automatic path will not.
- Inputs: journal files, `status.json` (halted, `foreign_edit` class, high-water mark), `operators.json` and `.prev`, key files and `.prev`, each service's rotation-state and verify-hash, the ledger. Outputs: the restore, forward or accept action; one ledger event; an alert; a summary and exit code that tell a halt from a failure.

## FAILURE MODES (each is evidence from a note or the code; the right column is the test that would kill it)
| # | Mode | Source | Test that kills it |
|---|---|---|---|
| 1 | `.prev` is a file the same unix user can write; a hash match against it alone proves nothing | C-71 D-6, C-29 obj. 1 | restore refused when `.prev` matches but one service says `none`; unreachable services treated as a halt (fail closed) |
| 2 | one wedged journal stops every identity (`_locked` resumes `journals[0]`, rotation.py:1098-1100) | C-71 D-6 | two identities, the first parked: the second still rotates (needs the park decision) |
| 3 | write storm: each failure writes two generations, the cap counts failures (rotation.py:160, :1356) | C-18 F-C18-1, C-29 obj. 3 | a loop of N reconcile attempts writes at most the capped number of generations (C-29 proposes 3 writes per identity per 24 h) |
| 4 | the frozen event schema cannot say WHICH reconcile action (`keyrotation.reconciled` fields: run fields, `operator_ids`, `generation`, `registry_sha16`; rotation_events.py:120) | C-29 obj. 4 | a schema test that the new action field is listed, and that an old reader still parses |
| 5 | accepting a foreign edit can launder a hostile edit | C-29 obj. 5, C-18 F-C18-3 | a roster edit that touches the in-flight row or the sealed row is not accepted; one that does not parse under the R1 parser is not accepted; a generation not above the high-water is not accepted |
| 6 | a lost `status.json` mid-rotation freezes the rotation as `foreign_edit` (it hashes `operators.json.prev`, which in flight is the pre-publish file) | C-843 F-C843-3 | delete status.json while in SOAK: later runs resume from the journal instead of skipping |
| 7 | a halt or skip raises no alert (rotation.py imports nothing from alerts; the `rotation_halted` class exists at alerts.py:151) | C-843 F-C843-9, F-PR57D-4 | a halt emits `rotation_halted` once; a repeat run does not repeat it the same day |
| 8 | `--downgrade-format` or `--abort-inflight` must not re-admit a retired hash (the verifiers refuse a hash that returns at or below the generation that removed it) | rotation.py header, R1 review F2, F6 | downgrade, then a service reads the old file: the old key is still refused; abort after PROMOTE restores nothing |
| 9 | `--extend` on the break-glass (sealed) row, or on a revoked one | rotation.py header (the sealed row is never a target) | refused with a named reason |
| 10 | a command racing the timer | design 4.2 (estate lock) | two processes, one lock; the loser exits without writing |
| 11 | R4b only: late reload, generation skew, proxy variables, uid mismatch, kill mid-SOAK | C-843, C-57 | the e2e assertions above, plus one case per mode |

## SIZE (in cards; each is one fail-first test file and mutants)
- R4b: about 5 cards: (1) the compose profile and made-up fixtures; (2) the happy-path e2e with a short soak; (3) kill mid-SOAK and resume; (4) the refusal assertions on all eight services; (5) the CI job for it (a workflow change: your call, and it would add run time to a 7-job pipeline). PLUS the prerequisites as separate cards: F-C843-3 to -6 and C-18 F-C18-5, -9, C-16 #6.
- R9: about 8 cards: R9.0 the foreign-edit remedy and the status rebuild from the journal (F-C18-3, F-C843-3); R9.1 the halt alert (F-C843-9; independent and cheap); R9.2 automatic reconcile states (a), (b), (c); R9.3 park semantics (mode 2); R9.4 the write cap; R9.5 `--abort-inflight` and `--extend`; R9.6 `--downgrade-format` and `--accept-roster`; R9.7 the event schema change (mode 4).
- Prerequisites for ARMING, not for merging (C-843): F-C843-1 compare-and-swap, F-C843-2 the ledger client's proxy.

## ORDER (recommendation; MEDIUM)
1. C-1157 (reviewer delta on rebase/57-c1156 648a933e) and the GX10 run, then land that branch (not PR 57's own head: six of its commits carry a personal address as the author name).
2. R9.1 (alert) and R9.0 (foreign-edit remedy): both small, both on the existing `halted` and `foreign_edit` paths; D-6 keeps halting until R9 exists, so R9.0 is what makes halting survivable.
3. The F-C843-3 to -6 fixes, then R4b: the first time the rotator meets real services, before any automatic restore exists.
4. R9.2 to R9.7 (the automatic and the command paths), tested in R4b's compose.
5. Arming only after F-C843-1 and F-C843-2 and Don's decisions below.

## DON'S DECISIONS THIS NEEDS (recommendations only; none made here)
1. Soak length (C-843 item 3): the code's soak is 15 min, not 24 h; the soak must outlast the longest time any consumer keeps the old key in memory (jobs in particular).
2. Park semantics (mode 2): parking an identity changes the "one rotation at a time" meaning for that identity only.
3. A schema change to the frozen `keyrotation.reconciled` event (mode 4), or leaving the action out of the ledger.
4. Whether `rotation.freeze` also pauses an in-flight rotation (C-843 item 3).
5. Whether `--accept-roster` may be automatic at all (mode 5) or stays a person's command.
6. Whether R4b's CI job is wanted in the 7-job pipeline.

## NOT DONE / UNCERTAIN
Did not read the whole of rotation.py (1693 lines) or all of C-843; did not run anything; do not know the design v0.2 text; the size is an estimate (LOW). C-12 (an older, open "R4b scope note" card) overlaps this note and can probably be closed by it: your call.
