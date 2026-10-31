# Builder Lane 11: status report to the coordinator (requested by Don)

## Delivered (each with a GX10 full run on the exact head, 16 suites, 0 failed or error lines)
| Card | PR | Head | What |
|---|---|---|---|
| C-32 (+C-671, C-819) | 347 | 10dfdef | edge-block checker sends the 15 extra C-27 probe shapes; 6 more as info lines; literal expectations. PR 347 is no longer open. |
| C-489 (+B-13, B-20, C-722, C-824, C-897) | 356 | 3361e01 | one `field_core.hosts.is_internal_host`; Don's rulings applied (canonical dotted quad only, metadata names refused, scope ids kept); stdlib copies in field_client, renew_token, estate_probe; `is_private`-family lint with one allowlist entry (force-gateway api.py:184) |
| C-590 (+C-830, C-886 C1, C-937, C-1010) | 363 | 02d1159 | VIDEO-SCRIPT speaks no test count, event count, drill timing or run time; figure-shaped pin |
| C-805 (+C-1003, taken over from archived Lane 2, Don's ruling) | 375 | 178af63 | an `svc-verifier-` row holding `bypass_operator_list` is refused at load; three tests that pinned the escape flipped; runbook pre-check |
| C-932 (+C-817) | 387 | 65a37a0 | compose_resolved_check: copied alone is exit 3; network_mode wording and pin; runbook pre-up line |
| C-821, C-823 | 349, 385 | (Lane 2's) | already built by Lane 2 (delivery note 20261105-1830); I added nothing |

All reports are in comms/inbox/coordinator/ (20261103-1130 through 20261108-2330). No force-push anywhere; every branch only moved forward. Branches for 356, 363, 375 and 387 are on older mains (63e91b2 / 5808a5c): re-cut under new names if they conflict.

## Open items on my side
- PR 356 CI green on 3361e01 (per Lane 15's table); reviewer deltas wanted on 356 (3361e01), 363 (02d1159), 375 (178af63), 387 (65a37a0). C-937's blocking condition on 363 was Python 3.14 CI on the head.
- Not built, owned elsewhere: force-gateway api.py:184 `is_private` migration (C-794 MEDIUM-HIGH: it also decides the REQUIRE_TLS_UPSTREAM refusal) waits for PRs 341, 352, 383; record_scenes.py:75 "Fifteen events" caption waits for PR 308; ~23 s / ~30 s demo timing in IMPLEMENTATION.md, phase-4.md, STATE.md (PRs 308, 338, 340, 342); wiring compose_resolved_check into CI (ci.yml).
- Blocked builder cards: C-757 (PRs 373, 360), C-758 and C-760 (PR 342). Other open builder cards are PR-author conditions for other lanes' PRs or Lane 13's C-773/C-774 (need PR 356 on main).
- Unverified anywhere: Python 3.11/3.13/3.14 ipaddress behaviour, the PR 356 + 368 merge after my rulings commit (Lane 15 saw it green before them), any operator environment holding short-form URLs (release note is in PR 356's text), the estate's real operators file (C-805).

## Process notes
- GX10 queue: other lanes' full runs overlapped throughout; my first C-489 run waited about 70 minutes; later ones started at load average under 5.
- I have polled the queue every 5 minutes since 2026-11-04 14:24; the last 47 minutes had no new comms commit and no new unblocked builder card. I will keep polling and take the next card at once (standing authorization, Lane 11).
