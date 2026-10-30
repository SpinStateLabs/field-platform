# PR 369 update for C-795, and two card notes (builder Lane 12)

## PR 369 (C-772): head 50ba99e3
GX10: FULL run on that exact head, 16 "== " suites, 0 failed|error. C-795 verdict: PASS WITH CONDITIONS on 1f4fbc7e; its three pin findings are closed with tests only (no code change in authn.py):
- F-C795-1 MEDIUM-LOW: `{x:path}` must match across slashes (a one-segment match would leave a multi-segment route open to a read key). Test added; mutant "one segment only" KILLED.
- F-C795-2 LOW: template literal parts are escaped (`/a.b/{x}` blocks `/a.b/1`, not `/aXb/1`); mutant "not escaped" KILLED. Added the over-block direction too: `{x}` is one segment (`/a.b/1/more` stays readable under an `/a.b/{x}` entry); mutant "`{x}` spans slashes" first SURVIVED, then KILLED by the extra route.
- F-C795-3 LOW: behind a root_path prefix `/api/health` is not an open path, so authn applies (fail closed). Pinned; no mutant run (no clean one-line mutant of that comparison).
Still open there, not mine to settle: F-C783-3 and F-C795-4 (one generic read key opens every service's reads; Don's call; adoption must pass `service=`), F-C795-5 (a standing test that fails when a GET handler contains a write-like call; I can take it with the adoption PR).

## Card notes
- C-803 (defence-shield `--allow-ip` refuses a catch-all) is ALREADY on main: `defence-shield/agent-incident-retro/src/agent_incident_retro/models.py:150-165` refuses a network wider than /8 (IPv4) or /32 (IPv6), `0.0.0.0/0` and `::/0` included, with tests in `tests/test_allow_ip_c240.py` and the README at lines 56-60 (C-240). One difference from the card: the message names the offending entry and the floor, not "the flag only". I did not claim it; suggest DONE, or a one-line follow-up if the card's wording is wanted exactly.
- C-806 (soak wording) touches docs/runbooks/v1.2-deploy-rollback.md and tasks/todo.md, which open PRs 290 and 342 (and 305, 308 for todo.md) also edit; not claimed.
- C-801 is PR 374 (reported separately). C-802 waits for PR 322; C-804 touches every service's api.py (open PRs on most of them); C-805 is Lane 2's.
