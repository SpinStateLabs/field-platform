# Don amends the Stage 2 R-1 condition (chat, question tool, 2026-11-07 ~00:25Z; recorded by the coordinator)

Question asked: Stage 2 is held because the R-1 rollback rehearsal needs REQUIRE already armed. Amend the condition: arm the GB10 kill-switch, then run the R-1 rehearsal first in the 1 h window with auto-rollback?
Don's answer: "Yes, arm then rehearse (Recommended)" (option A in the deployer's report 20261107-0015). The option text he chose also said: he confirms he has read B-7 and the compose-stop rollback command (checklist item 42).

Amended scope of the 20261107-0010 pre-authorisation (all else unchanged): arm the GB10 kill-switch ALONE under REQUIRE (build 41afda50, operators sha16 b885ebdab2948f13) now that the 41afda50 Stage 1 window is CLEAN (deployer, 00:02:04Z); run the R-1 rehearsal as the FIRST act of the 1 h Stage 2 window with auto-rollback armed; roll back on any rise in dropped_unauthenticated_records or dropped_refused_records or if the rehearsal fails. Stage 3 and Fly are NOT authorised.
Red-team: the NO-BLOCKER is on f7408db5; 41afda50 adds 852, 849, 834. The coordinator asks red-team for a delta check on 41afda50 in parallel; its absence does not block arming under option A (deployer's reading: not blocking), a BLOCKER from it would.
