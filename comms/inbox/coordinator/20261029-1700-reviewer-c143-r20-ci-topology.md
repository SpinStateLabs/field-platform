# C-143 / R-20 reviewer report: .github/workflows/ci.yml (610 lines) and tools/topology_lint.py (1,795 lines) on main 444e49b

VERDICT: the workflow is well hardened on token scope and action pinning; the weak points are unpinned Python installs, no job timeouts and no skip budget. One dated item will turn CI red on 2026-11-23 by design. I read ci.yml's header, the `tests` job and parts of the three smoke jobs, and topology_lint's header and allowlist; not all of either.

OBJECTIONS FIRST
1. "Unpinned" is a risk statement, not an observed failure: I did not see CI break on a dependency release.
2. I read about a third of ci.yml's smoke-job shell; a skipped assertion in the unread parts is possible.
3. I did not run topology_lint's nine entrypoint scenarios myself.

ASSUMPTIONS
1. Main 444e49b; ci.yml read at :1-90 in full, :146-158, :468-480, and its `grep` skeleton for permissions, `if:`, `|| true`, installs, timeouts; topology_lint.py :1-60 and the allowlist file in full (110 lines). [HIGH]

REASONING
1. Token and triggers (sound): `permissions: contents: read` at :12-13; `persist-credentials: false` on all four checkouts (:25, :92, :207, :368); triggers are `push` to main and `pull_request` (not `pull_request_target`, :7-10); no `secrets.` or `GITHUB_TOKEN` reference anywhere (grep); every `uses:` is pinned to a 40-hex SHA with a version comment (:23, :26, :90, :205, :366). [HIGH]
2. LOW, F-C143-1: unpinned installs: `python -m pip install --upgrade pip` (:31) and `pip install fastapi uvicorn httpx pytest` (:43) take whatever is latest on the day; `-e packages/field-core[dev]` (:32) resolves its own dependency ranges (pyproject) with no lock file or hash check. A release of fastapi/httpx/pytest changes CI results with no commit (the GX10 runs showed a starlette deprecation warning about httpx on every run). The four-Python matrix (:20-21, 3.11-3.14) multiplies the exposure. [HIGH on the lines; the risk is general knowledge]
3. LOW, F-C143-2: no `timeout-minutes` and no `concurrency:` on any of the four jobs (`tests` :16, `compose-smoke` :86, `fly-image-smoke` :199, `compose-upgrade-smoke` :348); the docker-compose jobs wait in shell loops (`wait_url`, 30 x 2 s) but a hung `docker compose build/up` runs to the 360-minute default; `runs-on: ubuntu-latest` floats (:17, :88, :203, :357). [HIGH on the absence]
4. LOW, F-C143-3: jobs can pass while skipping tests, with no budget. `pytest -q tools/tests` (:67) skips tests that need Windows PowerShell (the step's own comment: `test_field_rest_secret.py` "skips here"); my GX10 runs of the full `tools/tests` print "3 skipped" and sealed-ledger "4 skipped". Nothing fails the job if that number grows (no `-rs` report, no `--strict-markers`, no skip-count assertion), so a test turned into a skip by a missing tool passes green. The topology step is the counter-example: it "fails, never skips" if bash is missing (:74-76). [HIGH on the counts from my runs; MEDIUM on any currently unwanted skip: not enumerated]
5. LOW, F-C143-4 (links F-C141-1): defence-shield/agent-incident-retro is absent from the install list (:33-38) and every test step (:52-56, :67, :78-84): its 113 tests do not run in CI. [HIGH]
6. INFO, F-C143-5: the topology allowlist expires: `ALLOWLIST_MAX_AGE_DAYS = 30` (topology_lint.py:181); the only entries carry `verified_on: 2026-10-23` (allowlist.yaml), so the `Deployed-topology lint` step fails from 2026-11-23 unless someone re-verifies the live estate and bumps the date; the approver entry was added 2026-10-26 without a presence check (the file says so). By design; the coordinator should schedule the re-verification. [HIGH on the date arithmetic: 2026-10-23 + 30 days = 2026-11-22, red from the 23rd]
7. Smoke-job pattern checked: `out=$(... wget ... 2>&1 || true)` followed by `echo "$out" | grep -q 'HTTP/1.1 404' || { ...; exit 1; }` (:150-155, :472-476): the `|| true` only captures the output and a later assertion fails the step; sound. `if: always()` steps (:195, :343, :609) are log/cleanup. The per-service loop (:78-83) runs under the default `bash -e`, so a failing service stops the step (later services are then not run in that attempt, still red). [HIGH]

CONCLUSION
Add `timeout-minutes` per job, pin or constrain the pip installs (a constraints file), add a skip budget (`-rs` plus an assertion on the count, or `--strict` markers), run defence-shield, and put the 2026-11-23 allowlist re-verification on the coordinator's calendar. Not done: a full read of the smoke jobs and topology_lint.
