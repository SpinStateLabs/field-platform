# Lane 16: PR 421 (B-21) measured, run 41284958954 on a1491046: 11 of 11 green (Q-52 condition C1 met on that head; the newer head 849fdaef has its own run, in progress)

All figures HIGH, read from the public jobs API; durations are job started_at to completed_at; queue = run created (07:29:09) to job start.

| Job | queued | ran | tools step | other test step |
|---|---|---|---|---|
| tests (3.12, 2) | 0m51 | 8m48 | 4m18 | per-service 3m57 |
| tests (3.12, 1) | 3m20 | 8m41 | 4m46 | field-core 3m11 |
| tests (3.14, 2) | 4m50 | 11m44 | 5m36 | per-service 5m13 |
| tests (3.13, 1) | 11m26 | 7m52 | 4m32 | field-core 2m45 |
| tests (3.11, 1) | 11m47 | 8m26 | 4m41 | field-core 3m04 |
| tests (3.11, 2) | 16m35 | 11m42 | 5m29 | per-service 5m28 |
| tests (3.13, 2) | 17m15 | 11m37 | 5m32 | per-service 5m14 |
| tests (3.14, 1) | 17m35 | 8m14 | 4m33 | field-core 2m58 |
| three smoke jobs | 0m38 to 4m19 | 1m45 to 2m19 | | |

Run wall clock: 28m52 (07:29:09 to 07:58:01). Per job: shard 1 7m52 to 8m41, shard 2 8m48 to 11m44, against 16m19 to 19m42 per job on the last green main run before the change (41148860348). The jobs started in waves of 2 to 3 (07:30, 07:33, 07:40, 07:45), so the pool ran about four of these jobs at once and the last three waited 16 to 18 minutes: Lane 7's O1 holds, the queue sets the wall clock. The old run's queue was 22 to 32 minutes on a different load, so the two wall clocks (28m52 against 48m01 end to end) are not a controlled comparison; the per-job halving is. Shard 2 is the heavier half on 3.11, 3.13 and 3.14 (the per-service step plus the light tools files); moving test_estate_probe (38 s on the GX10) to shard 1 would balance it slightly; not done, the guard pins the list and the reviewer delta is pending.

Head 849fdaef (Q-52 fixes): run 41286521447, smoke jobs green, eight shard jobs in progress at 07:58Z, none red; I read it again at the 08:21Z check-in.
