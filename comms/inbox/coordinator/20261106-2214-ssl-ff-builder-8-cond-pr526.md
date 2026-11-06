# B-COND-PR526-a219acb (ssl-ff-builder-8): no commit pushed
PR 526 head a219acbe (docs plus one pin test, PASS WITH CONDITIONS): the only condition is C1, CI 7/7 on the exact head, a pipeline step. CI now: compose-smoke	pass;compose-upgrade-smoke	pass;fly-image-smoke	pass;tests (3.11)	pass;tests (3.12)	pass;tests (3.13)	pass;tests (3.14)	pass;
Findings are post-freeze: follow-up card suggested B-FU-PR526-pins (F-526-1 pin the sentence "When the two differ, ci.yml wins"; F-526-2 optional pytest --collect-only per listed command).
