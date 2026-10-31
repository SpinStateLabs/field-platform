VERDICT: PASS WITH CONDITIONS on a020c33dcecfea9412f1ff7fa74e774b0cfda445

Reviewer Lane 15, cloud-reviewer, C-970, PR 379 at a020c33 (same head as my C-966). UNVERIFIED: no GX10, CI not read.

## Objections first
1. "Unsafe if followed literally" cannot be proven by reading: I ran no step. I found no step whose text, followed literally, loses data or arms something unasked; the risks below are about reading errors, not wrong commands (MEDIUM).
2. The scripts the runbook relies on are outside the repository and unreviewed here; a literal reader depends on them behaving as described (not verified).

## Conditions still open on the newest head (merged state with main acaf5f2)
| id | open item | where | blocks a deploy step? |
|---|---|---|---|
| C-870 C1 build ids on neighbour lines | CLOSED (0 of 7 left) | whole file | no |
| C-870 C2 workstation name | OPEN here, closed by PR 342 | v1.2-deploy-rollback.md:938, :1302 | no (public safety only) |
| C-870 C2 home and profile paths | OPEN here, PR 342 scope (20 unix, 3 Windows lines) | e.g. :984, :1971, :1974 | a literal reader would run commands with a named account's paths on another host: yes, a wrong-path error, not data loss |
| C-870 C3 soaks | CLOSED by main (3 sites read five minutes: :925, :949, :1000) | | no |
| C-870 C4 deploys need Don's approval in chat | OPEN: no "in chat" text; sections 2 (:60) and 5 (:1047) open straight into commands | | YES in the process sense: a literal reader could start a deploy without the approval; the five "Don's go" lines cover arming steps only (:944, :968, :975, :1389, :1546) |
| C-870 F-6 stale file:line citations (5 of 10) | OPEN | e.g. agent_registry/api.py:232 and four more | no; misdirects a reader |
| C-906 deploy-status sentences | PARTLY: :484-485 now "observed on both estates at deploy time"; headline of section 7 now "arming is a separate step that needs Don's approval" | :484, :1093 | no |
| C-906 dated lines | 8 ISO dates remain (decision and ruling dates) | :3, :477, :480, :665, :1059-area, :1064, :1735, :1736, :1803 | no |
| outside scripts tagged "not in this repository" | CLOSED at every mention | :114, :927-928, :1032, :1259, :1267, :1291, :2058 | no |
| optional resolved-model compose check (PR 391) | not in this PR | | no |

## Would any step be unsafe if followed literally?
Only in the sense of the C4 row: the runbook never says a deploy needs Don's approval in chat before section 2 or 5, so a literal reader (human or agent) is not stopped. Irreversible steps carry explicit markers (A7 "IRREVERSIBLE for pre-F2 images", :944) and "Don's go" lines at arming steps. No step in the diff changes a command or flag (C-870 reading, unchanged by a020c33).

## Conditions
1. Add the approval sentence at the start of sections 2 and 5 (docs card, the one condition with safety effect). 2. Merge with PR 342. 3. Re-ground the five citations.

Not verified: any command, outside-script behaviour, CI.
