# Review PR #783 (crosswalk serve --every floor of 5 s, S8-25) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `8494fe4dbe8093f47175f6359f48b30305363fc8` (base main; PR is NOT a draft). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 6 files: compliance_crosswalk/api.py (+10/-1), cli.py (+9/-3), tests/test_every_floor.py (+71), tests/test_regwatch.py (2 lines), docs/ENVIRONMENT.md, README.md. Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- `MIN_EVERY_SECONDS = 5`; `create_app(every=n)` raises ValueError for 0 < n < 5; `crosswalk serve` prints one error line and exits 2 before importing uvicorn or building the app; 0 and negative still mean off. Only adds a refusal; the estate value (86400, compose/Fly defaults: docker-compose.yml:132, docker-compose.gb10.yml:415, fly/entrypoint.sh:65) is untouched.
- Existing test edit (every=2 to every=5 plus the /health assert) is the minimum needed; I found no other caller using a positive value below 5 in the repo (grep of py/sh/yml/md).
- Deviation from the card (floor 5, not 60) is disclosed, reasoned (soak runs; sealed-ledger observer minimum 5) and is one constant. Whether 5 or 60 is Don's decision (not in source).
- tests/test_every_floor.py: 17 passed on the head. Full crosswalk suite (PR: 384 passed, 7 skipped) not run by me.
- Operational note: a soak run that set FIELD_CROSSWALK_EVERY to 1 to 4 would now fail to start (exit 2). Disclosed in the README paragraph.

## Mutants (api.py / cli.py, one at a time, restored after each; one malformed first attempt discarded)
| # | Mutant | Result |
|---|--------|--------|
| M1 | floor 4 | RED |
| M2 | floor 6 | RED |
| M3 | api `<` to `<=` | RED |
| M4 | api check removed | RED |
| M5 | api refuses 0 as well | RED |
| M6 | CLI check removed | RED |
| M7 | CLI exit code 1 | RED |
| M8 | CLI also refuses negatives | RED |
| M9 | CLI `<` to `<=` | RED |
| M10 | CLI message text changed | RED |
Totals counted from the table: 10 mutants, 10 RED, 0 SURVIVED.

## LOWs (optional, new PR)
1. Non-integer `FIELD_CROSSWALK_EVERY` remains a typer usage error (pre-existing, unchanged).
2. Process note: the PR is marked ready, the other S8 PRs are drafts.
