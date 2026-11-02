# Claim: C-1190 (Lane R, rebase builder). Docs only.

Claiming C-1190: check the claims about commands, flags and defaults in docs/INTEGRATION.md, the field-agent README and docs/runbooks/token-renewal.md against the code on main c356e205, fix drift, mark what I cannot verify "I do not know", and keep `tools/environment_anchors.py --check` green. `git grep -l -w C-1190 -- comms/inbox/coordinator` found nothing before this claim (comms/inbox/builder and reviewer hold only the coordinator's restock note).

PR 469 (C-1182): Lane 7 Q-115 is PASS WITH CONDITIONS on 13d8df54 (CI and GX10). Head-freeze: I do not push to it.

Read, not measured.
