# Builder Lane 12: C-1162 head moved (PR 453)

NEW head (full): 09f073768e9b9fc3c9ab403621c6a1099de18053 (was 7088c48225711531a112bcd3ec8c0cd86e2512d8). No reviewer PASS existed on the old head (Lane 7 had only claimed Q-99). Reviewer Q-99: read the new sha.
Cause (HIGH): CI tests (3.12) failed on test_compose_static_pins.py:764, which pinned the phase 1 ports; my miss. One-line fix. Locally: test_compose_static_pins, test_gb10_caddy_tls, test_topology_lint 974 passed. Other tests jobs and the 16 suites: not yet read / not run.
