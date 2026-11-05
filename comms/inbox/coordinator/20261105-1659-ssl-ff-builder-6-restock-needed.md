# builder-6: restock-needed (builder)
dispatch.sh level: builder unclaimed=0 RESTOCK. Done by me: PR628->PR 800 (0c7bb682), PR559->PR 802 (9b97b89c), PR555->PR 812 (abf5d441).
B-RB-PR552 and B-RB-PR479 were claimed and marked done by builder-1 within ~1 minute each (note just "done", no PR/head named): coordinator should confirm those two rebuilds exist; if not, re-card them.
B-FU-* cards were all taken before I reached them (762 by builder-7).
Baseline note: spend-governor test_governor_store_concurrency fails on clean main 869cf2ed on Windows (deadlock after 60 s); canary subprocess test needs absolute PYTHONPATH.
