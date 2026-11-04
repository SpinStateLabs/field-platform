# Reviewer note (FALLBACK, read-only): MERGE 24 = main cd3b7690 (batch m1b: PR 477 C-1191 CI anchors step, PR 476 C-1189 kill-switch 422s)
Reviewer: ssl-ff-reviewer-4. UNVERIFIED (cloud, no GX10). Read-only; nothing pushed outside comms. Delta: 793481f3..cd3b7690, 6 files (+177/-3), 4 commits; author and committer of all 4 = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 on all 4 (HIGH). The merge is done; this is an independent check after the fact. I did not re-run the recorded GX10 A 16/16 or the Lane 15 PASS.

Correction to my MERGE 23 note (review-merge23): it says "trailers per the table below" and there is no such table. The facts: of the six commits of 4ef319cc..793481f3, five (b2b7cfd6, 968cc2c0, cc985147, 9010866f, 1ad562bb) carry a Sonnet 5.5 trailer and the merge-batch commit 793481f3 carries none; all six have the Don Hagell noreply identity.

## Objections first
1. A CI step that runs a read-only check is only a gate if it cannot be softened and the command it runs is the real one; the batch pins both with a test that reads the workflow text. That test cannot show GitHub Actions executes the step (it states this limit).
2. Installing the field-core 422 handler changes every 422 of the kill-switch, including the halt/drill/revive routes an operator uses in an incident; a wrong handler would change the error an operator sees. The handler is shared and already measured on nine other services.
3. The line-number anchor in docs/ENVIRONMENT.md for FIELD_KILL_ENDPOINT_ALLOWLIST moved 293 -> 294 with the import; the new CI step is what keeps such anchors honest, and it is itself new.

## Verified (run by me)
- Baseline at cd3b7690: tools/tests/test_ci_anchors_step_c1191.py, test_422_handler_installed_c1114.py, services/kill-switch/tests/test_422_no_echo_kill_switch_c1189.py and tools/tests/test_yaml_duplicate_keys.py: 133 passed.
- Code read: kill_switch/api.py imports `install_validation_handler` and calls it on the served app right after `install_authn(app)` (2 lines); the CI step is `python tools/environment_anchors.py --check` in the `tests` job, after the topology lint and before the service suites.
- field-core http_errors tests (packages/field-core/tests/test_http_errors_c1018.py): 19 passed.

## Mutants (scratch worktree at cd3b7690; kill = at least one failure in the four files above)
| # | Mutant | Result | Killed |
|---|---|---|---|
| K1 | kill-switch: handler not installed | 27 failed | yes |
| K2 | kill-switch: handler installed on a throwaway `FastAPI()` | 25 failed | yes |
| K3 | kill-switch: handler call under `if False:` | 25 failed | yes |
| H1 | handler echoes `input` | 29 failed | yes |
| H2 | handler names the caller's extra key (the extra_forbidden redaction removed) | 133 passed | NO (equivalent, see below) |
| H3 | handler drops `loc` | 17 failed | yes |
| H4 | handler blanks `type` | 8 failed | yes |
| H5 | fixed-message kinds no longer keep their message | 133 passed | NO (killed by field-core tests, see below) |
| Y1 | CI step runs `--fix` | 2 failed | yes |
| Y2 | CI step `continue-on-error: true` | 2 failed | yes |
| Y3 | CI step `if: always()` | 2 failed | yes |
| Y4 | CI step removed | 3 failed | yes |
| Y5 | CI step duplicated | 3 failed | yes |
| Y6 | CI command path typo | 3 failed | yes |
| Y7 | CI command `|| true` | 2 failed | yes |
| T1 | guard list: kill-switch dropped from MEASURED (test-list mutation) | 1 failed | yes |
Totals counted from the table: 16 mutants, 14 killed by the delta's own four files, 2 survived them (H2, H5). Survivors against the field-core handler suite (19 passed at baseline): H5 is KILLED there (1 failed, 18 passed); H2 survives it too (19 passed) and is equivalent: the earlier loc filter already replaces any string that is not a known field name with the redaction word, so the extra `extra_forbidden` rewrite changes nothing for a caller-chosen key. So 15 killed overall, 1 equivalent survivor. I did not run the whole kill-switch suite or the other 15 suites.

## Findings
- None blocking. F-C1189-1 LOW: the kill-switch tests assert the declared field is named with type `string_type` and a string message, but not the message text; the text is pinned by field-core's own suite (H5), so nothing to add here.
- F-C1191-1 LOW: stated limit of the CI-step test (reads workflow text; does not run Actions); nothing to fix.

## Verdict (retrospective, no head to freeze): no objection to MERGE 24
Every claimed behaviour (handler installed on the served app, 422 never repeats the caller's text, field name kept, the CI step present, exact, not softenable, not duplicated, the command red on a stale anchor and green on a good one) is killed under mutation.
