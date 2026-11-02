merge assistant 1 addendum to batch m1a (head 3baf65bc5477400d25177b151ef402da463f8996, main 4ef319cc unchanged at 2026-11-02 18:15 local):
- Checked now: m1a (6 files: ci.yml, docs/ENVIRONMENT.md, kill-switch api.py + its test, test_422_handler_installed_c1114.py, test_ci_anchors_step_c1191.py) shares NO file with s2q 793481f3 (13 files); git diff --name-only against main, HIGH. The two can stack in either order.
- m1a touches docs/ENVIRONMENT.md (PR 477's ci.yml change or PR 476's api.py line shifts); it is the only ENVIRONMENT.md batch of mine. Not checked: the file:line pins in tools/tests against ENVIRONMENT.md, which the GX10 run covers.
- GX10 report for m1a: none yet.
