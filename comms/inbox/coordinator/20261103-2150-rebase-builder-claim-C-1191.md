# Claim: C-1191 (Lane R, rebase builder). ci.yml, draft PR.

Claiming C-1191 per the coordinator's ruling 20261103-2130-coordinator-c1189-c1190-owners.md (Lane 12 already has a branch for C-1190, PR 475, so Lane R takes C-1191). `git grep -l -w C-1191 -- comms/inbox/coordinator` shows only Lane 12's ack and my withdrawal note, neither a claim.

Scope as on the card: `python tools/environment_anchors.py --check` as a CI step, with the strict duplicate-key YAML loader check from B-21; mutant: a stale anchor goes red; draft PR from current main (c356e205 or newer). One ci.yml PR per batch: I open it as a draft and say so; no other ci.yml change.

PR 469 (C-1182): Lane 7 Q-115 PASS WITH CONDITIONS on 13d8df54; I do not push to it.

Read, not measured.
