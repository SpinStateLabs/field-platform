# Assistant verdict table, 20261106-0800 (coordinator-assistant)

Method: heads and CI from `gh pr list --json statusCheckRollup` at about 21:29Z 2026-10-30 (system clock). Verdicts parsed from the first line of every inbox report; a parse miss is shown as such (MEDIUM confidence on the Note column; HIGH on head and CI). Cloud (Lane 14/15, UNVERIFIED) reports never gate. 69 open PRs.

## Next batch BZ (PR 386, draft): PR 290, PR 319, PR 328. Open batch BY: PR 376 (CI 5/7 in progress).

## Escalations (one line each)
- HEAD MOVED after verdict: see Note column (57, 308, 316, 336, 340, 342, 343, 346, 349, 351, 358, 360, 361, 363, 365, 367, 369, 372, 374 among others).
- CI queued or running over 90 min: PR 356 (queued 108 min, run 41117235958), PR 371 (queued 124 min, run 41115100224), PR 366 (in progress 158 min, run 41110404705).
- PR with no CI checks: PR 330, 348, 359 (no runs for the head).
- CI failed: PR 297 (tests 3.12, known flake note), PR 331 (3/7 FAILURE, no verdict on head).
- Verdict conflict on one head: PR 326 (FAIL C-791 vs PASS WITH CONDITIONS C-770/C-729 on da33a9a; all cloud).
- PR 329 is CLOSED unmerged; C-585 said merge 329 first (F-C589-1/-2); PR 328 in BZ carries that as condition (2), follow-ups PRs 345/353/370/385.
- PR 305 and PR 308 duplicate Phase E work; PR 318/330 superseded by 381.

| PR | head | CI | Note |
|---|---|---|---|
| 57 | 30ac1e1 | 7/7 | HEAD MOVED: verdicts on 11c55c7 only |
| 290 | 33b2c02 | 7/7 | VERIFIED on head: C-447 L7 PWC; in BZ |
| 297 | 3bb2510 | 6/7 FAILURE | no merge verdict; tests 3.12 red (flake note in inbox) |
| 305 | b484e7d | 7/7 | L6 PWC on this head (wrong test figure F-PR305-1); duplicate of 308, only one may merge: coordinator decides |
| 308 | fc8b363 | 7/7 | HEAD MOVED: L6 PWC was on e881626 |
| 315 | ba26a96 | 7/7 | C-509 PWC on head, NOT RECOMMENDED for batch (take PR 295 branch); duplicate of 311 line |
| 316 | 6ae698f | 7/7 | HEAD MOVED: C-515 (cloud) PWC on 9b1fb08 only |
| 317 | 9cc5221 | 7/7 | head has cloud-only c865 PASS (UNVERIFIED, no gate) |
| 318 | 4383a07 | 7/7 | superseded by PR 381 (C-862); do not batch |
| 319 | 34895a4 | 7/7 | VERIFIED on head: C-593 L6 PASS; in BZ |
| 322 | 6ac0f8e | 3/7 IN_PROGRESS,QUEUED | head has cloud-only c864 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 325 | 5955870 | 7/7 | head has cloud-only c879 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 326 | da33a9a | 7/7 | CONFLICT on one head: C-791 FAIL vs C-770/C-729 PWC (all cloud, no gate); delta da33a9a (C-642) stays open |
| 327 | dc0fc85 | 7/7 | no verdict parsed |
| 328 | 7679259 | 7/7 | VERIFIED on head: C-585 L5 PWC; in BZ |
| 330 | f0e9e70 | NONE | superseded by PR 381 (C-862); do not batch |
| 331 | 4014720 | 3/7 FAILURE | HEAD MOVED: verdicts on 1a45db0 only |
| 332 | 0df2259 | 7/7 | no verdict parsed |
| 333 | f34d092 | 7/7 | HEAD MOVED: verdicts on 39f8636 only |
| 334 | 8bea8c4 | 7/7 | no verdict parsed |
| 335 | fc73f64 | 7/7 | HEAD MOVED: verdicts on 2e00c73 only |
| 336 | 08463bd | 0/7 QUEUED | HEAD MOVED: verdicts on fe6c2be only |
| 337 | 72e8fae | 7/7 | HEAD MOVED: verdicts on c3fd144 only |
| 338 | f052a0e | 7/7 | no verdict parsed |
| 339 | 0219998 | 7/7 | HEAD MOVED: verdicts on ab709ed only |
| 340 | 25ffdc1 | 0/7 QUEUED | HEAD MOVED: verdicts on 1643d20,bde88a2 only |
| 341 | b6f9b61 | 7/7 | head has cloud-only c768 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 342 | 43b421a | 7/7 | head has cloud-only c793 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 343 | 30015c3 | 7/7 | HEAD MOVED: verdicts on 1f93620 only |
| 344 | 627532e | 7/7 | head has cloud-only c861 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 345 | f3787c9 | 7/7 | head has cloud-only c765 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 346 | ef19210 | 5/8 IN_PROGRESS,QUEUED | head has cloud-only c868 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 347 | 10dfdef | 7/7 | head has cloud-only c796 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 348 | 7d332d1 | NONE | HEAD MOVED: verdicts on 6b685fd,db9bad0 only |
| 349 | ba35c14 | 0/7 QUEUED | HEAD MOVED: verdicts on 50c87b9 only |
| 351 | 31e92be | 0/7 QUEUED | HEAD MOVED: verdicts on 354a081,af1e7cc only |
| 352 | c28167c | 7/7 | head has cloud-only c867 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 353 | 5d5cbf7 | 7/7 | head has cloud-only c798 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 355 | fdc299c | 7/7 | head has cloud-only c852 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 356 | a9be069 | 3/7 IN_PROGRESS,QUEUED | head has cloud-only c858 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 357 | b2f3b16 | 7/7 | head has cloud-only c753 PASS (UNVERIFIED, no gate) |
| 358 | 07bd6d6 | 6/7 IN_PROGRESS | HEAD MOVED: verdicts on d5d4fc6 only |
| 359 | 8948389 | NONE | head has cloud-only c863 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 360 | c876f6d | 0/7 IN_PROGRESS,QUEUED | HEAD MOVED: verdicts on 3aacd5a,b2bc129 only |
| 361 | 7525a93 | 0/7 QUEUED | HEAD MOVED: verdicts on 5a58ee8 only |
| 362 | b468f79 | 7/7 | HEAD MOVED: verdicts on 54c5b86 only |
| 363 | 380bc30 | 4/7 QUEUED | HEAD MOVED: verdicts on 3b28331 only |
| 364 | beb3a7a | 7/7 | head has cloud-only c754 PASS (UNVERIFIED, no gate) |
| 365 | d570c31 | 1/7 QUEUED | HEAD MOVED: verdicts on 39303a9 only |
| 366 | 3436007 | 5/7 IN_PROGRESS | head has cloud-only c799 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 367 | 46bc0d9 | 1/7 QUEUED | HEAD MOVED: verdicts on e2ce179 only |
| 368 | 1f7f61f | 7/7 | head has cloud-only c790 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 369 | 57a356b | 0/7 QUEUED | HEAD MOVED: verdicts on 1eb21c7,1f4fbc7,7551327,f685e08 only |
| 370 | 1381b56 | 7/7 | head has cloud-only c787 FAIL (UNVERIFIED, no gate) |
| 371 | 8eb5c87 | 3/7 IN_PROGRESS,QUEUED | head has cloud-only c860 FAIL (UNVERIFIED, no gate) |
| 372 | 1b8f9e3 | 0/7 QUEUED | HEAD MOVED: verdicts on 90881a5,b069869 only |
| 373 | 8c3cfb5 | 7/7 | head has cloud-only c856 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 374 | 09abbe3 | 0/7 QUEUED | HEAD MOVED: verdicts on 1eb21c7 only |
| 375 | 4ff09c7 | 0/7 IN_PROGRESS,QUEUED | HEAD MOVED: verdicts on 561ce2a only |
| 376 | 5777030 | 5/7 IN_PROGRESS | batch BY; cloud C-854/C-873 PWC on head; GX10 batchby run: coordinator's |
| 377 | dfceabc | 4/7 QUEUED | head has cloud-only c875 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 378 | 6727f5b | 5/7 IN_PROGRESS | head has cloud-only c874 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 379 | a3cc199 | 0/7 QUEUED | head has cloud-only c872 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 380 | 7551327 | 2/7 IN_PROGRESS,QUEUED | head has cloud-only c871 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 381 | b00bd96 | 2/7 QUEUED | head has cloud-only c876 PASS WITH CONDITIONS (UNVERIFIED, no gate) |
| 382 | a5dd7ff | 2/7 IN_PROGRESS,QUEUED | no verdict parsed |
| 383 | 2b22bac | 0/7 QUEUED | no verdict parsed |
| 384 | ca41545 | 0/7 QUEUED | no verdict parsed |
| 385 | 112cf16 | 0/7 QUEUED | no verdict parsed |
Generated with Claude Code
