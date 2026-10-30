# C-533 (Lane 9, cloud-reviewer, read-only, no GX10): docs/runbooks/ntfy-alerts.md against packages/field-core (alerts.py, cli.py) and docs/ENVIRONMENT.md, main b929f12

VERDICT: of 21 statements checked, 15 TRUE, 2 PARTLY TRUE, 1 STALE, 3 UNVERIFIABLE. The delivery mechanics, configuration variables, content rules, class table and CLI exit codes match the code. One finding matters: the runbook says the platform sends alerts for rotation failures, overdue rotations, break-glass use and stage transitions, but nothing in main calls `alerts.send` for any class except the test alert, and no service merges `health_fields()` into `/health`. One public-safety class finding (a personal local path). No secret read or printed; the topic file was never opened.

OBJECTIONS FIRST: (1) "Sent by: rotator ..." may describe the intended wiring of cards still unbuilt (the rotator is PR 57, held); that makes it a plan, not a defect, but the runbook's second sentence says "The platform sends push alerts" in the present tense. (2) My "no caller" result is a repository-wide grep over *.py, *.sh, *.yml, *.md; a caller written in another language or built at deploy time would be missed. (3) I read the code; I did not run it or the tests (no GX10). (4) The ntfy documentation claims in section 5 are external facts, read on 2026-10-28 by the author; I did not re-fetch them.

ASSUMPTIONS: main b929f12; alerts.py (626 lines), cli.py `alert-test` and `alert-topic-init`; tests in packages/field-core/tests/test_alerts_ntfy.py.

TRUE
1. Variables: FIELD_NTFY_TOPIC_FILE, FIELD_NTFY_TOPIC, FIELD_NTFY_BASE_URL, FIELD_NTFY_TOKEN_FILE, FIELD_NTFY_TOKEN: alerts.py:77-81; all five are listed in docs/ENVIRONMENT.md (5 matches). File first, env only when no file (alerts.py:11-19). HIGH.
2. Only https, plain http only to loopback; no redirects followed; no token means a topic under 20 characters is refused as guessable: alerts.py:27-28, :88 (`MIN_TOPIC_LEN_WITHOUT_TOKEN = 20`), :351 (`topic_guessable`), :430 (redirect handler). HIGH.
3. Class table, priorities and tags: alerts.py:127-160 matches the runbook's seven rows (rotation_failed 5, rotation_overdue 4, breakglass_used 5, stage_transition 4, stage_aborted 5, rotation_halted 5, test 3; tags identical). HIGH. (The runbook's tags column for `stage_transition` is `arrow_right, field`: matches.)
4. Test alert title "FIELD TEST ALERT - no action needed" and body start "This is a TEST alert": alerts.py:155-158. HIGH. (The 6-hex test id is not in this block; not checked.)
5. Content check: withheld when outside charset, containing `fok_` or `tk_`, a 12+ hex run, a 32+ opaque run, a PEM header, or the topic or token; the 12-digit decimal side effect follows from `[0-9A-Fa-f]{12,}`: alerts.py:110-113, :34-37. HIGH.
6. Delivery: POST with Title, Priority, Tags; default deadline 5 s, cap 30 s; 3 attempts default, cap 5; back-off 1 s then 2 s; retry on timeout, network error, 429 and 5xx only; response body never read: alerts.py:93-98, :472, :548-585. HIGH. Body cap 1,024 bytes: alerts.py:100. HIGH.
7. Failures never silent: counters and the ERROR log line with fixed reasons: alerts.py:199-256 (`alerts_failed`, `alerts_last_failure_reason`, `alerts_last_failure_class`, `alerts_last_failure_at`), :331-351 (reason strings). HIGH.
8. `field alert-test` and `field alert-topic-init --out [--force]` exist; test takes `--estate`; the command refuses to overwrite without `--force`: cli.py:150-166, :175-187. HIGH. Exit codes 0 / 1 / 2 as documented: cli.py:158-160 docstring. HIGH (docstring read).
9. Topic is `field-` plus 192 random bits, url-safe: alerts.py:611. HIGH (38 characters: 6 + 32 from 192 bits base64-url: arithmetic consistent; not run).
10. No ledger rows written by the module; the topic never in a log, result or `/health`: alerts.py:49-51 (module docstring); counters carry only classes and reasons. MEDIUM-HIGH (read, not each log line).
11. The named test `test_content_carries_no_secret_key_token_hash_or_topic` exists: packages/field-core/tests/test_alerts_ntfy.py:351. HIGH.
PARTLY TRUE
12. Section 3 "Sent by": the class wording is in code, but no sender exists for six of the seven classes (finding F-C533-1). `breakglass_used`, `rotation_failed`, `rotation_overdue`, `rotation_halted`, `stage_transition`, `stage_aborted`: each is defined in alerts.py:131-155 and not called anywhere outside tests. `test` is sent by `alert-test` (cli.py:163). HIGH (grep).
13. "A long-lived caller merges `field_core.alerts.health_fields()` into its `GET /health`": the function exists (alerts.py:235-256); no service does so (grep: only cli.py calls it). The sentence describes how to use it, so it is true as an instruction and false as a description of the platform. HIGH.
STALE
14. Section 3 intro and the opening paragraph: "The platform sends push alerts for key-rotation failures and overdue rotations, break-glass use, Phase G stage transitions": present tense, but see rows 12-13: on main only the test alert can be sent. The 2026-10-28 date of the runbook precedes any wiring; the rotator that would emit `rotation_failed` and `rotation_halted` is PR 57 (held for rework, C-496). HIGH.
UNVERIFIABLE FROM THE REPOSITORY
15. Every "VERIFIED (docs)" line in section 5 (ntfy publish, priority, tags, topics, tokens, limits of 4,096 bytes and 250 messages a day, FCM logging): external pages; not re-read here.
16. "Don subscribes ... instant delivery": a human procedure; and BOOTSTRAP step 4 "the step is done when the TEST alert shows up on Don's phone": the runbook itself says no real delivery has been proven by any test.
17. The P36 automatic-arming condition: a decision record outside src.
PUBLIC-SAFETY (class and place only)
18. A personal Windows user path appears twice in BOOTSTRAP steps 1 and 3 (`C:/Users/<name>/.field-local/ntfy-topic.txt`, lines 19 and 31): a private machine path in a public file, the same class the docs-accuracy report F-DOC-4 had removed from README. It is not a secret and not the topic, but it names a person's account. Generalise to `<path-to-topic-file>`. HIGH (read). No estate address, flag value, build SHA or topic value found in the file.
19. The runbook names a person ("Don installs the ntfy app", "Don's phone"): operator role, not a secret; mention only because the public-safety card C-540 asks for people and addresses.
20. The file names the hosts `gb10` and `fly` only as `--estate` examples: no address.
21. Date check: "Read on 2026-10-28": consistent with the repository's comms start; no conflict.

FINDINGS (for cards)
- F-C533-1 MEDIUM (code gap, a feature: Don decides): six of seven alert classes have no sender on main, so the "alerts are live" condition of P36 cannot be met except for the test alert. Needs a card per sender or a runbook note "wired as each card lands".
- F-C533-2 MEDIUM-LOW (doc): rows 12-14: change "The platform sends" to the present truth (library and test command only; senders land with the rotator and the stage controller) and say no service merges `health_fields()` yet.
- F-C533-3 LOW (public-safety): row 18: remove the personal path (two places).
- F-C533-4 LOW (doc): the section 3 table's "Sent by" column should say "planned" for each class until a sender exists.

CONCLUSION: the alert library is built as documented (HIGH, read) but is wired to nothing in main; the runbook reads as though it is live (HIGH, repo-wide grep). Confidence: HIGH for rows 1-14 and 18; "I do not know" for the external ntfy facts and for whether any estate-side script (outside this repository) calls the library.
