# Reviewer report: PR 473 @07e0176b (ROADMAP test count and STATE.md refresh through MERGE 20, C-1184)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Docs-only PR (ROADMAP.md, STATE.md): no behaviour to mutate, so no mutant table; I checked every cite against its source instead.

## Verdict: PASS WITH CONDITIONS (head 07e0176b565a68c81d0ab6a1a264bcb78449c7df)
Conditions: C1 rebase on current main (PR base is cddca526, main is 97dcfec1); C2 the text says "through MERGE 20" but STATUS now records MERGE 24 (cd3b7690), so the refresh is 4 merges stale on landing; the coordinator decides whether to land as is (it is honest about its scope) or ask for MERGE 21 to 24 lines; C3 light GX10 run, "light run, docs only", and CI green.

## Objections first
1. The count is a point-in-time figure; main has moved 4 merges, so ROADMAP's "10,410 on cddca526" is already not main's number (HIGH, STATUS top entries).
2. "Collected" is not "passed"; the text says so itself (HIGH, read).
3. The per-suite sum depends on a collection path; the text discloses a first pass with one shared path that errored in two suites (HIGH, read). Not a risk to the figure.
4. The first 18 commits after a9dc4f3 are not itemised; stated as "I do not know their PR numbers" (HIGH, read). Honest gap, not an error.

## Checks run
1. Merge lines: compared MERGE 1 to MERGE 20 PR numbers, batch names and card numbers with comms/STATUS.md entries (read from origin/comms). All match: MERGE 1 361,366; 2 413,412; 3 317,331,332,333,337,338; 4 349,363,373,375; 5 322; 6 356; 7 382,388,394,423,424; 8 401,403,404; 9 334,335,347; 10 407,406,396,393,378,377; 11 336; 12 381,341,325; 13 358,359,348,402; 14 432 (C-1116); 15 431 (C-1114); 16 446 (C-1154); 17 438 (C-1122), 433 (C-1087); 18 447 (C-1158); 19 442 (C-1128); 20 461 (C-1163). main cddca526 = MERGE 20 head: matches (HIGH).
2. Arithmetic: the 18 per-suite counts sum to 10,410 (1542+808+256+291+242+191+3855+311+263+97+374+448+269+255+457+315+207+229; running total checked step by step) and there are 18 suites (HIGH).
3. Re-collected 5 of 18 suites on the exact head with `pytest --collect-only`, per-suite relative PYTHONPATH: field-core 1542, sealed-ledger 808, lifecycle-manager 269, kill-switch 242, conformance-sentinel 263. All five equal the text (HIGH). The other 13 suites were not re-collected (not verified: some need packages missing in my cloud environment).
4. Public-safety: no added line carries a 40-hex id, flag, credential or deploy status; the only IP-shaped strings in STATE.md are older lines outside the diff (HIGH).
5. `tools/environment_anchors.py --check`: 0 wrong anchor rows. 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH).

## Findings
- F1 LOW: C2 staleness; no wrong statement.
- F2 LOW: "Test count ... 8,308 on a9dc4f3" is kept as history; consistent with the old ROADMAP line (HIGH).

## Not verified
13 of 18 suite counts; rebase on 97dcfec1; CI.
