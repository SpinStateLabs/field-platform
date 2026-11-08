# Review R-PR956-dfcc6b8
**VERDICT: PASS WITH CONDITIONS — head dfcc6b8de7ebebd09f2102f65aa8b31a9f450ff7** (PR 956, rebuild of #825 / card C-607; reviewer fp-reviewer-c)

## Identity / scope (HIGH)
- `gh pr view 956` headRefOid = dfcc6b8de7ebebd09f2102f65aa8b31a9f450ff7 = checked-out sha. One commit; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files: docs/runbooks/v1.2-deploy-rollback.md (+87/-83), tools/tests/test_deploy_docs.py (+1/-1), tools/tests/test_operator_mounts_b6.py (+1/-1). Nothing under .github/. `git diff --check` clean. Merge with main 16fc921e8: no conflict (diff computed against it; base is current).
- Independence: I did not build it. Read the whole diff.

## What the diff does (HIGH)
Replaces workstation name, GB10 account/home path, user-profile paths, build ids, dated runs and estate ledger heads with placeholders (`<control-workstation>`, `<gb10-home>`, `<gb10-account>`, `<build-id>`, `<date>`, `<time>`); tags scripts as not in this repository; adds two "A deploy needs Don's approval in chat" lines; retitles §7; adds one NEW cite (see condition 1). Tests: header anchor `<control-workstation> (Windows PowerShell 5.1)` and `<gb10-home>/.field-local/keys/svc-<name>/svc-<name>.key`.

## Scrub completeness on the head (HIGH, grep of the runbook)
rog-command 0, spinner 0, donal 0, `C:\Users` 0, `/home/` 0, `D:\claude` 0, gmail 0, bare 7-hex build ids 0 (one false positive: a sentence at line 951). IPs left: loopback/0.0.0.0 only. `fly.dev`: only `force-field-sandbox.fly.dev` (the allowed sandbox hostname, lines 909, 1668). Dates left (2026-09-12 at line 3, 2026-09-13, 2026-11-02, 2026-11-05, 2026-10-27/28, 2026-10-23 at line 1916) are decisions/rulings and a mutation-run date, not estate state; MEDIUM that none is estate status (not every one read in context).

## Mutants (scratch worktree, never the PR branch; tests: test_deploy_docs.py + test_operator_mounts_b6.py, 54 pass on the head)
Rounds 1-2 combined; "all occurrences" rows replace every occurrence because the key-path appears in many lines of §7.

| # | Mutant | Result |
|---|---|---|
| 1 | header anchor -> `rog-command (Windows PowerShell 5.1)` | KILLED (13 fail) |
| 2 | header anchor -> `<control-workstation> (PowerShell 7)` | KILLED (13 fail) |
| 3 | header anchor typo `<control-workstn>` | KILLED (13 fail) |
| 4 | header anchor `<workstation>` | KILLED (13 fail) |
| 5 | key path -> `/home/spinner/...` (all occurrences) | KILLED (1 fail) |
| 6 | key path `<gb10-hom>` typo (all) | KILLED (1 fail) |
| 7 | key path `.../key/` dir (all) | KILLED (1 fail) |
| 8 | key path `/home/other/...` (all) | KILLED (1 fail) |
| 9 | key path -> spinner, FIRST occurrence only | SURVIVED (test needs just one `<gb10-home>` occurrence) |
| 10 | key path typo, first occurrence only | SURVIVED |
| 11 | key path dir, first occurrence only | SURVIVED |
| 12 | key path `/home/other`, first occurrence only | SURVIVED |
| 13 | delete the approval line in §7 | SURVIVED (no test pins it) |
| 14 | revert new cite to `api.py:326 -> reject_reserved_event_type` | SURVIVED (no test pins it) |
| 15 | reintroduce `spinner` in `<gb10-account>` sentence | SURVIVED (no test) |
| 16 | reintroduce `rog-command` in the backup-copy line | SURVIVED (no test) |

Totals counted from the table: applied 16, killed 8, survived 8, not applied 0. Rows 9-12 are an artefact of single-occurrence mutation (the test asserts membership, so a surviving duplicate satisfies it); rows 13-16 are real: nothing keeps the scrub from regressing (condition 2, optional).

## Lints (HIGH for counts)
- Runbook-related set on the head (test_deploy_docs, test_gb10_caddy_tls, test_machine_verifier_identity, test_operator_mounts_b6, test_phase_g_check, test_runbook_pins_c465, test_runbook_trust_cites_sd2, test_stage_controller, test_environment_doc, test_boundary_echo_lint_c505): 399 passed, 89 errors in one run. All 89 were `RuntimeError: harness did not come up` in test_phase_g_check.py (my concurrent runs contended). Re-run of test_phase_g_check.py alone on the head: 106 passed (exit 0). Same file alone on main 16fc921e8: 1 failed, 105 passed (a pre-existing failure on main, not the PR).
- Earlier docs lints (test_docs_no_line_cites_sd1 etc.) passed in my PR 951 review on a different head; not rerun here on this head: test_docs_no_line_cites_sd1 covers only ARCHITECTURE.md/IMPLEMENTATION.md, not the runbook.
- Full tools/tests not run to completion (suite takes tens of minutes on this host).

## Conditions
1. **New line-number cite, unverified by a pin.** The PR replaces `sealed_ledger/api.py:326 -> operator_auth.reject_reserved_event_type` with `sealed_ledger/api.py:372-400 -> operator_auth.admit_ledger_event`. On the head, `services/sealed-ledger/src/sealed_ledger/api.py` lines 372-400 contain the `append_event` handler start and the comment naming `operator_auth.admit_ledger_event`, and `admit_ledger_event` exists at field_core/operator_auth.py:619 (HIGH). The cite is correct today, but it is a text change beyond the scrub's name; the PR body says nothing about it ("scrub only"). Condition: state it in the PR body (or the report) as an intentional correction from #825's text. It is not a blocker.
2. Optional (new PR only): a one-line test that the runbook holds none of the scrubbed tokens (`rog-command`, `spinner`, `donal`), since mutants 15-16 survive.

## Other LOWs
- Commit message carries a `Claude-Session:` claude.ai session URL trailer in a public repo (not a secret; MEDIUM that it is harmless). Consider omitting it.
- Two `GB10`/`Fly` ledger-head placeholders now read `<build-id>` for ledger heads (lines ~55-56): placeholder name is inexact (a ledger head is not a build id). Cosmetic.

## Verdict
PASS WITH CONDITIONS (condition 1 is a PR-body note, not a head change). Head frozen at dfcc6b8de7ebebd09f2102f65aa8b31a9f450ff7; any change must be a condition fix; optional items go in a NEW PR.
