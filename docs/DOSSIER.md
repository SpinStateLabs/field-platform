# DOSSIER — FIELD Platform

Maintained by the ssl-fp-docs agent. Principal: Don (AICTO, Spin State Labs).
Last pass: 2026-11-04, against main `cd3b769` (2026-11-02). Anything not
traceable to a cited file or `git log` is marked **not in source**. This file
indexes; it does not replace `STATE.md` (history), `ROADMAP.md` (what is
built) or `CHANGELOG.md` (what changed).

Pass 6: 2026-11-21, against main `cb7a94f`. Adds the ledger load track (T5-T8)
below; the rest of this file was not rechecked this pass.

## Goals
- Reference implementation of the Force Field Protocol: FORCE (runtime prompt
  protocol) and FIELD (design-time governance). Source: `README.md`.
- Make FIELD v1.0's declared governance enforced, with an Enforced-vs-Declared
  table per service. Source: `README.md` "The honesty line".
- Spin State Labs product line and the University of Waterloo AI-CTO capstone
  initiative. Source: `README.md`.

## Status (verified from the tree, 2026-11-04)
- 14 service directories under `services/`: the 12 systems, `ops-console`,
  `claude-approver` (flags OFF). Source: `ls services`, `README.md`, `ROADMAP.md`.
- Packages: `field-core`, `field-agent`; also `defence-shield`, `tools/`,
  `agents/` (two SSL agents), `manifests/`, `plugins/field-agent`.
- v0 trio (Sentinel, Gateway, Crosswalk): deterministic cores shipped, ADR delta
  built. Source: `ROADMAP.md`.
- Current recorded phase in `STATE.md` "Current phase": v1.2 12-system closure
  (started 2026-09-12). Whether it is formally closed: **not in source**.
- Since 2026-10-29 main carries hardening only (no-echo 422s, operator-pair
  guard, redirect/proxy pinning, anchor tooling, public-safety scrubs). Source:
  `CHANGELOG.md` Unreleased, "main from 2026-10-30 to 2026-11-02".
- `main` is red since 4d03b2a (PR 532): the C-57 proxy-lint test flags `tools/start_role_session.py`. Evidence and proposed patch are in the comment on PR 539; not fixed (code change, outside the docs lane). Source: CI run 41812420379, local run on `origin/main`.
- Estate (GB10, Fly) deployment status is deliberately not stated in docs
  (commit 968cc2c). **Not in source** by policy.

## Ledger load track, T5-T8 (added 2026-11-21, main `cb7a94f`)
- Trigger (2026-11-20 estate finding, from the T6 task brief): during one heavy
  authenticated request (`/attest/pack`, `/ledger/verify` or an unfiltered
  `/ledger/events`; about 11,200 events, 5.7 MB) all eight monitored `/health`
  answers failed for 11-63 s. The estate monitor uses a 5 s timeout and two
  failed polls in a row trigger an enforcement rollback. Source:
  `docs/capstone-evidence/t6-health-under-load.md` (the "Production finding"
  paragraph).
- T5, `ba86175` (#1074): `estate_probe` `--timeout` / `FIELD_PROBE_TIMEOUT` for
  every request; whole-ledger routes on a large estate take 5-18 s. Source:
  `tools/estate_probe.py` (the comment above `DEFAULT_TIMEOUT`).
- T6, `95cd964` (#1075): harness `tools/health_under_load.py` (loopback only)
  and evidence `docs/capstone-evidence/t6-health-under-load.md`. Result: partly
  reproduced on the Fly image under Docker CPU limits; the sustained
  all-service failure was **not** reproduced.
  - No lock, blocked event loop or single worker (HIGH).
  - The ledger process does the CPU work: one `/attest/pack` is 16 `GET /events`
    plus one `GET /verify`, each a full-chain parse (HIGH).
  - Services are coupled through the machine's CPU quota (MEDIUM): at Fly's
    6.25% shared baseline every `/health` slowed together and the ledger's
    reached 5 s once.
  - Under that load `/attest/pack` answered HTTP 200 with 19 of 26 metrics
    `unavailable` (attest's 10 s timeout to the ledger) (HIGH, observed once).
- T7, `787de47` (#1076): per-store parse cache keyed on each segment's exact
  bytes, plus a `/verify` result cache. A pack parses each line once instead of
  17 times (`services/sealed-ledger/tests/test_ledger_head_cache_t7.py`). Capped at
  `PARSE_CACHE_MAX_BYTES` (32 MiB raw). Measured locally:
  - at 1 CPU, `/attest/pack` 2.36 s -> 0.37 s cold, 0.16 s warm;
  - at the 1/16 CPU baseline, `/verify` 19 s -> 1 s, but the pack still takes
    about 20 s (one run per cell, MEDIUM).
  Source: PR #1076 body (the timings); `services/sealed-ledger/README.md` T7
  paragraph (the mechanism and the cap).
- T8, `cb7a94f` (#1078): T7's `/verify` cache answered `ok` after an archive
  copy of a rotated segment was altered or deleted, because
  `Snapshot._verify_archived` reads files outside the cache key. Found in the
  T7 post-merge review. Fix: a ledger with any archived segment is verified on
  every call; the parse cache still applies. Source: commit `cb7a94f` message,
  `services/sealed-ledger/tests/test_verify_cache_archived_t8.py`.
- Open: whether T6-T8 change the estate's behaviour is **not in source**, and
  deploy status is not stated here by policy (see Status, last bullet). The mechanism is
  unconfirmed until the estate measurements in open question 7 are taken.
- After this pass: T9, `49a171a` (#1080), set the Fly machine's `[[vm]]` to
  `cpus = 4` (`cpu_kind = "shared"`) in `integration/fly/fly.toml`. T6 and T7
  were measured against the 1-shared-CPU size, so their 6.25% baseline figures
  describe that size, not the current config. Source: `git log`, `fly.toml`.

## Decisions on record
- 2026-09-13, Don: `FIELD_CROSSWALK_EVERY=86400` on both estates. `STATE.md` "Current phase".
- 2026-10-05, Don: Fly and GB10 keep separate `FIELD_SHARED_SECRET` values. `STATE.md` ops-console 0.2.0 entry.
- 2026-10-21, Don: ADR-0072 accepted, option 3 (estate kill watcher). `STATE.md`.
- 2026-11-03, Don (Q-86 F1): company contact stays in plugin/marketplace metadata and the invoicing skill; client mailboxes stay scrubbed. Commit 793481f.
- Standing: log-only first, enforce after the measured gate; the 2-week burn-in / 30-day false-block window is NOT running by decision. `tasks/todo.md` header, `STATE.md` Next action 2.
- Standing: never claim compliance or certification; crosswalk stays suggestion-only behind human sign-off. `tasks/lessons.md`.

## Drift register (found this pass)
| # | Doc | Drift | Action |
|---|-----|-------|--------|
| 1 | `CHANGELOG.md` | Stopped at PR 159 (2026-10-29); 110 commits after it unrecorded | Fixed this pass |
| 2 | `docs/DOSSIER.md` | Did not exist | Created |
| 3 | `ROADMAP.md` Notes | Test count was 8,308 (a9dc4f3, 2026-10-30) | Fixed pass 3: 10,390 collected at cd3b769, 2026-11-04, Python 3.13, 18 suites (field-core 1546, tools 3802, sealed-ledger 808, others 97-457, field-agent 207, defence-shield 229). Figure goes stale per commit; see open question 4 |
| 4 | `STATE.md` Open questions | OQ-1, OQ-2, OQ-5 read as open; the Phase gate log records the hardening pass that addressed them (OQ-2 partly: ISO 42001 pending purchase) | Open: edit by the STATE.md owner; docs agent flags only |
| 5 | `STATE.md` | 2,282 lines; 2026-10-04 section sits above the 2026-08 baseline; "Next action" items 1 and 2 carry 2026-09 dates (token re-mint before 2026-10-08) | Open: needs Don's call on archiving |
| 6 | `README.md` | "12 systems" plus 2 directories is consistent with the tree; no drift found | None |
| 7 | `docs/ARCHITECTURE.md` | Pass 5 (2026-11-04) corrects pass 2. The count claim holds (ops-console reads twelve services: twelve `FIELD_*_URL` reads). The line cites do not: the 2026-11-01 C-1114 commits (each service's `install_validation_handler`) shifted every `api.py`. Wrong at cd3b769: registry `api.py:187` (now `create_app`, ~161), ops-console `api.py:377-398` (now `_RefusalLedger`, ~476), gateway `:563`/`:617` (+1) and the five event lines `:545 :572 :633 :651 :711` (+1), crosswalk `api.py:224-232` (+1), ledger `api.py:234-239` and `:576-582` (+1 to +2) | Fixed: those cites now name the symbol, as the ADR 10 notes already do (85958f1). Kept as line cites, checked correct: gateway `api.py:36-39`, `:25-37`, `retention.py:87`, lifecycle `cli.py:187`/`:211`, claude-approver `core.py:19-21`. Nothing tests ARCHITECTURE cites, so they drift again unless pinned (open question 6) |
| 8 | `README.md` Definition of Done | Every `services/*` has `SPEC.md` and a LIMITS section in its README; only `claude-approver` has no `demo.sh`. README scopes the DoD to "each system" and excludes claude-approver from the 12, so no contradiction | None; noted |
| 9 | `.github/workflows/ci.yml` | README says CI runs py 3.11-3.14; PR #520 shows four `tests (3.x)` jobs for 3.11-3.14 | None |
| 10 | all `*.md` (87 files) | Pass 3 link and path scan: 0 broken relative links (2 hits are literal `(url)` text in the incident-retro README); 7 backticked repo paths do not exist: `integration/demo/.env` x3 (gitignored runtime file, fine), `docs/archive/` (proposed in this file), `plugins/force/skills/force/protocol.md` (force-gateway README; ADR 10 note names the other repository), `packages/field-agent/.../canary.py` (elided path, fine), `docs/proposals/03-...md` (deployment_agent README) | Fixed the last: README now says the path is not in this repo. The `tools/deployment_agent/__init__.py` docstring carries the same path; code, not touched |
| 11 | `docs/capstone-evidence/t6-health-under-load.md` | Added 2026-11-21. Its "Production finding" paragraph names the estate's image tag, a build id. Open question 5 quotes the `comms/PROTOCOL.md` public-files rule as banning build ids in public files; `comms/PROTOCOL.md` was not re-read this pass | Open: a one-line scrub on Don's go (open question 9). The doc came from the T6 track |
| 12 | `services/sealed-ledger/README.md`, `LedgerStore._verified` docstring | Added 2026-11-21. T7 called the `/verify` result a pure function of the cache key; false once a segment is archived | Fixed by T8 (`cb7a94f`) |

## Open questions for Don
1. Close v1.2 formally in `STATE.md`, or is it still open? Recommendation: record a closure entry with the date and commit, since main shows hardening only.
2. Archive `STATE.md` history older than the v1.2 start into `docs/archive/`? Recommendation: yes, keep the top 300 lines current; it is 165 KB and one section contains non-UTF-8 bytes that make `grep` treat it as binary (use `grep -a`).
3. Re-attestation: `STATE.md` states the first agent falls due 2026-11-06 at the 90-day default. Today is 2026-11-04. Confirm the attest runs are scheduled. Not in source whether they are.
4. Test-count policy for `ROADMAP.md`: refresh per release, or drop the figure. Recommendation: drop it or pin it to a CI run id, since a collected count goes stale per commit.
5. `docs/ROLE-AGENTS-TEAM-ACCESS.md` and `tools/start_role_session.py` (PR 532) publish a workspace id, an environment id and five agent ids in a public repository. Whether that is allowed under the public-files rule in `comms/PROTOCOL.md` ("no estate address other than the sandbox fly.dev hostname, no flag value, build id, deploy status or credential") is not decided in source; the ids are not credentials as far as I know (MEDIUM). Recommendation: the coordinator or reviewer rules on it; this agent did not edit the files.
6. Pin `docs/ARCHITECTURE.md` cites the way `tools/environment_anchors.py` pins `docs/ENVIRONMENT.md`, or accept that line cites there drift on every service edit. Recommendation: cite by symbol only (done for the drifted ones) and add a test that each cited symbol still exists; a builder card, since it is test code.

7. (2026-11-21) Take the T6 estate measurements before judging T7/T8:
   - Fly `cpu_balance` and `cpu_throttle` around a heavy request;
   - `/health` polled from inside the machine and through the edge at the same
     time (inside fast but outside failing points at the edge or proxy; both
     failing points at the VM);
   - the `/ledger/health` check history for the same windows.
   Recommendation: yes. Without them the 2026-11-20 mechanism stays MEDIUM.
8. (2026-11-21) Under CPU starvation `/attest/pack` returns HTTP 200 with most
   metrics `unavailable` (T6). Keep that, or answer non-200 when the ledger was
   unreachable? Changing it is an API change. Recommendation: decide, then
   write a builder card.
9. (2026-11-21) Scrub the image tag from the T6 evidence doc (drift row 11).
   Recommendation: yes, as its own docs PR.

## Roadmap pointers
- Built: `ROADMAP.md`.
- Backlog in rough priority: `STATE.md` "Next action" (tunnel/Tailscale in front of :18080 with the shared secret ON; ledger anchor scheduling; signing-key rotation; ISO/IEC 42001 ingest; EUR-Lex manual cross-check). Dates in that list are as of 2026-09; verify before use.
- Alert senders: six alert classes have no sender (`CHANGELOG.md`, `docs/runbooks/ntfy-alerts.md`).

## Process (source: `origin/comms`, `comms/PROTOCOL.md` and `comms/ROLE-LOOP.md`, read 2026-11-04)
- The coordinator is the only session that merges, deploys or edits STATUS, TASK-QUEUE and WORKLIST. A merge needs an independent reviewer PASS and a green GX10 run on the exact head.
- Docs work: addition-only dated entries, one item = one branch = one draft PR, no code changes. Fallback when no card exists: check one README or runbook against the code and fix the first contradiction.
- PR 520 was merged by the docs agent on Don's explicit chat instruction, without a reviewer PASS or a CI run (CI was queued). Reported to the coordinator the same day; status of the follow-up check: not in source.

- 2026-11-20: T7 (#1076) was merged with green CI on its head but without a
  reviewer PASS (PR #1076 has no reviews recorded). The post-merge review found
  the archived-segment `/verify` cache defect that T8 (#1078) fixed. Source:
  PR #1076 review list, commit `cb7a94f` message.

## Maintenance loop
Each pass: diff `git log` since the last CHANGELOG entry; recheck counts against the tree; update the drift register; log corrections in `tasks/lessons.md`.
