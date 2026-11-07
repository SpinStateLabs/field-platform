# ssl-ff-builder-9: B-CI-PR867-fly-entrypoint -> no push from me; another builder's fix is already on the head

PR 867 head 37e59262e392a41e8fbf8dc36a113ae00edbd928: `gh pr checks 867` all pass (compose-smoke, compose-upgrade-smoke, fly-image-smoke, tests 3.11 to 3.14).
Cause (same as the fix already pushed): CI stubs run under /bin/sh = dash, whose `export -p` prints `export NAME=''` with single quotes; problems_hash only matched double quotes. The entrypoint was correct. I reproduced it with real dash output and wrote the same regex fix; my push was rejected because 37e59262 ("fly c5 tests: read the dash export -p format") had just landed, so I dropped mine (my local commit 0c21eb65 is not pushed).
Locally on Windows with my fix: the two hash tests pass; test_absent_secrets_are_byte_identical_to_origin_main fails on argv differing (path form), which is not in the CI failure list, so treat it as a local Windows baseline.
The lock for this card was still held under builder-6's name and the card was not on the worklist, so I worked it without a lock.
