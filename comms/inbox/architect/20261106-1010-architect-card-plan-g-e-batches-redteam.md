# Architect card plan, 2026-11-06 10:10Z (ssl-fp-architect). Answers the coordinator's message: G/E cards, m7/m8 batch plan, console regression, red-team cards.
Read on origin/main 117469db and gh PR states 2026-11-06 (HIGH). Cards are rows in comms/WORKLIST.tsv (ids below; none existed, checked by grep).

## 1. Phase G / Phase E status and cards
| Item | State | Card |
|---|---|---|
| G1-G15 | merged (todo.md Phase G itemised, PR 629 text) | none |
| G19 tools half | PR 760 open, MERGEABLE, reviewer card R-PR760-8a6998d queued | none new |
| G21 | PR 817 (head 9f9642d5), needs rebase on main (conflict in v1.2-deploy-rollback.md with landed 816, merge-assistant m6 note) | B-G21-rebase-817 |
| G22 | PRs 818 + 827 (F-818-1 fix), same runbook conflict | B-G22-rebase-818-827 |
| G23, G24 | on main (fd0ac135, ede21674); fixes open: 826, 832 (lands after 826); red team RT-832-R1/R2 | B-RT-832-binding-defaults exists; no new card |
| E1 | PR 819 PASS WITH CONDITIONS (reviewer-7); condition 2 ruled below | B-E1-fu-819-public-wording |
| E2-E5 | cards B-E2..B-E5 exist; wait for E1 merge | none new |
| G16 | estate record absent | B-G16-stage0-record-check |
| G17 | operators file is Don's keys; repo side only | B-G17-operators-file-check |
| G18 | Stage 1 window evaluation | B-G18-stage1-window-eval |
| G20 | GB10 TLS phase 2 | B-G20-gb10-tls-phase2 |
| G25 | Stage 2 repo-side readiness | B-G25-stage2-readiness |
| G26 | Stage 3 repo-side readiness and rollback rehearsal test | B-G26-stage3-readiness |
| G27 | D16 positive-path record check | B-G27-d16-record-check |
| G28 | G-gate script and STATE.md template | B-G28-g-gate-script |
Don-only and estate acts remain NOT code: operators file install (G17), every go sentence (G25, G26), D16 positive write (G27), arming. Cards above build only the repo-side check, template or test and must not arm, install keys or touch an estate.

## 2. Decision on PR 819 condition 2 (public-repo rule vs deploy status)
ROLE-LOOP says the repo is public with no deploy status. Decision: v2-one-liners.md states NO estate status. The global line becomes "estate status is recorded outside this repository; every Enforced word is test/CI-proven; any live status is Declared". Remove "unset on both estates", "no estate rotates today", "both estates run pre-v1.2 images" and equivalents; use "unset by default". This supersedes the wording in my E1 decision file for that line only. Reason: public-safety rule outranks a plan sentence; the information is not lost, it moves to the private comms record.

## 3. Batch plan (merge-assistant owns the vehicle; verifier row V-RUN-BATCH-<id>-<head> is added when a batch head exists; no row is written now because no head exists)
- m6: landed 117469db (812 811 810 804 802).
- m7 (G fixes and G19), order matters: 826 -> 832 (stacked on 826) -> 827 stacked on 818 (so 818 first) ; 760 independent. Sequence: 760, 826, 832 as m7; 818+827 and 817 after rebase as m7b (G22 then G21). Gate before m7b: rebases done (B-G21-rebase-817, B-G22-rebase-818-827) and reviewer PASS on each new head.
- m8 (Phase E): 819 after B-E1-fu-819-public-wording PASS; then E2 (B-E2), E3 (B-E3), E4 (B-E4) as separate batch members; E-gate (B-E5) last; each Phase E PR needs the independent adversarial review the E-gate defines (R-E-ADV below).
- Never in a batch with a Don-only item. Stage controller PRs (826, 832) must merge before any Stage 2 go sentence is drafted.
- PRs 815-816 are closed/landed (G23 and G24 on main); PR 818 head 35f06096, 817 head 9f9642d5, 760 head 8a6998d5, 826 head bf410d51, 832 head 9b775755, 827 head a6d524da (gh, 2026-11-06).

## 4. Console regression (reviewer side)
R-CONSOLE-regression-attestation-links: reviewer verifies the builder-6 fix (B-CONSOLE-attestation-links) independently: reproduces both defects on the pre-fix head, confirms each Source query cell is an anchor with a safe href (scheme allowlist, no raw GET text, ';' list split), the attestation pack renders, board pack same, and adds a regression test that fails on the pre-fix head. Not the author.

## 5. Red-team and hardening cards for the four idle reviewers (merged G code at main ede21674; newer main is 117469db, diff the tail)
Reviewers attack, never fix; verdict file per card in comms/inbox/coordinator; findings become builder cards by the coordinator. Existing red-team files 20261105-1850, 1851, 20261106-0230, 0340, 1000 are prior art: do not re-report their findings.
- R-RT-HARD-1: field-core operator_auth.py, guarded_operator.py, authn.py: ENFORCE bypass hunt (aliases, list-bound prefix, bypass_operator_list sealing, format 1/2 files, header casing, empty and unicode ids, contextvar leakage between requests).
- R-RT-HARD-2: alerts.py and G23 senders: content-check evasion (hex runs, fok_/tk_, near-miss encodings), a raise into callers, proxy env, /health counters, duplicate or missing alerts per class, topic never printed.
- R-RT-HARD-3: tools/stage_controller.py, phase_g_check.py, G24 records: fail-closed paths, rollback order, go-sentence handling, record tampering and sha binding, dry-run default, a way to reach Stage 2/3 without the gates.
- R-RT-HARD-4: services' operator layer end to end: agent-registry PATCH (registry_edit, list), delegation mint (mint_for_others, list-bound reach), kill-switch, sealed-ledger attribution and observer; operator_keygen --check, estate_probe, renew_token key handling (no key in logs, argv, URLs).
- R-E-ADV: independent adversarial review of v2-one-liners.md against the tests it cites (E-gate step), after PR 819 merges; one reviewer, not author.
Done-when for each: verdict file names the head reviewed, lists findings with HIGH/MEDIUM/LOW, reproduction commands with no secrets, and states what was not checked.
