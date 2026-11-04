# DOSSIER — FIELD Platform

Maintained by the ssl-fp-docs agent. Principal: Don (AICTO, Spin State Labs).
Last pass: 2026-11-04, against main `cd3b769` (2026-11-02). Anything not
traceable to a cited file or `git log` is marked **not in source**. This file
indexes; it does not replace `STATE.md` (history), `ROADMAP.md` (what is
built) or `CHANGELOG.md` (what changed).

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
- Estate (GB10, Fly) deployment status is deliberately not stated in docs
  (commit 968cc2c). **Not in source** by policy.

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
| 7 | `docs/ARCHITECTURE.md` | Pass 2 (2026-11-04): ops-console reads "twelve services" and the twelve named match the twelve `FIELD_*_URL` reads in `services/ops-console/src/ops_console/api.py:430-452`; no drift | None |
| 8 | `README.md` Definition of Done | Every `services/*` has `SPEC.md` and a LIMITS section in its README; only `claude-approver` has no `demo.sh`. README scopes the DoD to "each system" and excludes claude-approver from the 12, so no contradiction | None; noted |
| 9 | `.github/workflows/ci.yml` | README says CI runs py 3.11-3.14; PR #520 shows four `tests (3.x)` jobs for 3.11-3.14 | None |

## Open questions for Don
1. Close v1.2 formally in `STATE.md`, or is it still open? Recommendation: record a closure entry with the date and commit, since main shows hardening only.
2. Archive `STATE.md` history older than the v1.2 start into `docs/archive/`? Recommendation: yes, keep the top 300 lines current; it is 165 KB and one section contains non-UTF-8 bytes that make `grep` treat it as binary (use `grep -a`).
3. Re-attestation: `STATE.md` states the first agent falls due 2026-11-06 at the 90-day default. Today is 2026-11-04. Confirm the attest runs are scheduled. Not in source whether they are.
4. Test-count policy for `ROADMAP.md`: refresh per release, or drop the figure. Recommendation: drop it or pin it to a CI run id, since a collected count goes stale per commit.

## Roadmap pointers
- Built: `ROADMAP.md`.
- Backlog in rough priority: `STATE.md` "Next action" (tunnel/Tailscale in front of :18080 with the shared secret ON; ledger anchor scheduling; signing-key rotation; ISO/IEC 42001 ingest; EUR-Lex manual cross-check). Dates in that list are as of 2026-09; verify before use.
- Alert senders: six alert classes have no sender (`CHANGELOG.md`, `docs/runbooks/ntfy-alerts.md`).

## Process (source: `origin/comms`, `comms/PROTOCOL.md` and `comms/ROLE-LOOP.md`, read 2026-11-04)
- The coordinator is the only session that merges, deploys or edits STATUS, TASK-QUEUE and WORKLIST. A merge needs an independent reviewer PASS and a green GX10 run on the exact head.
- Docs work: addition-only dated entries, one item = one branch = one draft PR, no code changes. Fallback when no card exists: check one README or runbook against the code and fix the first contradiction.
- PR 520 was merged by the docs agent on Don's explicit chat instruction, without a reviewer PASS or a CI run (CI was queued). Reported to the coordinator the same day; status of the follow-up check: not in source.

## Maintenance loop
Each pass: diff `git log` since the last CHANGELOG entry; recheck counts against the tree; update the drift register; log corrections in `tasks/lessons.md`.
