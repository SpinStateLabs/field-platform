# groomer: C-1202 reconcile proposal (queue and BACKLOG against the reports since C-1139). Proposal only; the coordinator edits TASK-QUEUE.md.

Method: read MERGE 16 to MERGE 23 in comms/STATUS.md, the OPEN/CLAIMED lines of comms/TASK-QUEUE.md (185 lines, C-1139 to C-1202), and per card `git grep -l -w` over comms/inbox/coordinator plus the claim file names. Read, not measured: no PR contents were opened for this note. Confidence tags: HIGH = stated in a MERGE line, MEDIUM = inferred from a report, LOW = not found.

## 1. Landed: propose DONE (evidence in STATUS.md)
- C-1154 PR 446 (MERGE 16). HIGH.
- C-1122 PR 438 and C-1087 PR 433 (MERGE 17, batch cb25). HIGH.
- C-1158 PR 447 (MERGE 18, batch cb26). HIGH.
- C-1128 PR 442 (MERGE 19). HIGH.
- C-1163 PR 461 (MERGE 20). HIGH.
- C-1173 PR 459 (MERGE 21, batch cb28): the MERGE line says "part 2", so confirm part 1 landed earlier before marking DONE. MEDIUM.
- C-1183 PR 470 (MERGE 22). HIGH.
- C-1130 PR 440, C-1134 PR 448, C-1182 PR 469 (MERGE 23, batch s2q). HIGH.
- C-1106: PRs 427 and 428 closed as superseded by main (MERGE 18, with Don approval). HIGH; mark DONE or SUPERSEDED as the coordinator prefers.
- Reviewer cards answered by a report named in a MERGE line: C-1124 (Lane 7) and C-1126 (Lane 17) in MERGE 17. HIGH. C-1123 (Lane 7; MERGE 18 applies its F3 ruling) and C-1151 (Lane 15; MERGE 22 says C-1183 pins its survivors). MEDIUM.

## 2. Not landed even though a MERGE line names them (keep OPEN)
- C-1131 (PR 342 guard: "comes next" in MERGE 23). C-1196 (PR 441, "held out" in MERGE 23; PR 441 has a Lane 15 revised PASS on 56f2f1fa). C-1187 and C-1188 (follow-ups named in MERGE 20; C-1188 has no claim and no report). C-1176 (follow-up after the batch). C-1052 (rulings applied only). HIGH.

## 3. Superseded batches
- s2p (PRs 440, 448, 469 on 4ef319cc): superseded by s2q, which landed as MERGE 23 (the coordinator note to the verifiers says the s2p run is superseded). HIGH. s2q itself landed: DONE, not superseded.
- cb24 (cb23 + PR 433 on 05942b98): superseded by cb25 (MERGE 17). MEDIUM (from the merge-assistant and verifier notes; no STATUS line names cb24).
- cb27 (PR 459 on 6385f877): superseded by cb28 (MERGE 21). MEDIUM, same reason.
- m1a (PRs 477, 476): stopped by GX10 verifier A; m1b is the live batch (verifier A 16/16 on cd3b769, 448e7e4). HIGH.

## 4. Claim collisions
Resolved by a ruling or a withdrawal on file: C-1163 (Lane 13 withdrew; PR 461 landed), C-1172 (owner Lane 12, 20261103-1330-coordinator-c1172-owner-lane12.md), C-1197 (Lane 12 owns, coordinator ruling 89541ed; Lane 1 and Lane 13 withdrew), C-1189 to C-1191 (20261103-2130-coordinator-c1189-c1190-owners.md). HIGH.
Still open, no coordinator ruling found by card id: C-1165 (Lanes 11, 12 and the rebase builder claimed it) and C-1179 (Lanes 11 and 12). LOW: I did not read the contents, only the claim file names; C-1176 is named in the field-mcp batch ruling 20261103-1600 and is probably settled.

## 5. Unstarted by id
- No report names them at all: C-1188, C-1198, C-1199, C-1200, C-1201 (C-1202 is claimed by this groomer).
- Named once, no claim file: C-1141, C-1155, C-1170 (probably only the restock note). LOW.

## 6. Limits
185 OPEN/CLAIMED lines is more than I could read card by card. Many cards with reports are probably done or superseded but not named in a MERGE line (for example reviewer and verifier cards); I did not mark those. BACKLOG.md: I flip Q items as reports arrive; Q-115 was the last stale one found.
