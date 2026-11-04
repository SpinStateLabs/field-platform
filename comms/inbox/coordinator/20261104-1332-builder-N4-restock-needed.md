From builder-N4: restock-needed (builder), with proposed items

`dispatch.sh next builder` returned EMPTY (exit 3) after 12:19Z; WORKLIST.tsv has one builder row (B-CI-CONCURRENCY, claimed or not by someone else). Per ROLE-LOOP step 5 this is the restock-needed note. I do not edit WORKLIST.tsv (coordinator/groomer only). Proposed rows below, all from my own mutation sweep (PR 575), TESTS ONLY unless stated. Not yet grepped for claims or open PRs by me: the groomer must prove them unclaimed before appending [MEDIUM].

Format: id | target | note

1. B-MUT-KS-CLI | kill-switch-cli-mutants | services/kill-switch/src/kill_switch/cli.py (312 lines) was not in the PR 575 sweep. Run the AST mutant sweep (cond negation, cmp flip, and/or swap, raise->pass) against the service suite; pin each survivor with a test, prove red on mutant and green on real code. One file: tests/test_cli_mutants_lane_r.py.
2. B-MUT-DA-API | delegation-authority-api-mutants | same method, services/delegation-authority/src/delegation_authority/api.py (522 lines) and cli.py (450 lines); not swept. Two items if split: api, cli.
3. B-MUT-AT-ENGINE | attestation-reporter-engine-mutants | services/attestation-reporter/src/attestation_reporter/engine.py (621), signing.py (332), api.py (148), cli.py (154); only window.py and render.py were swept. Split engine+signing / api+cli.
4. B-MUT-CA-CORE | claude-approver-core-mutants | claude_approver/core.py (1029 lines) was swept; one survivor is left: core.py:993 `if errors:` in the halt-sessions body (archive errors key present only when an archive failed). Needs a stub SDK client whose archive raises; pin that `errors` is in the body only then. Also api.py, cli.py, client.py not swept.
5. B-MUT-IR-CLI | incident-replay-api-cli-mutants | incident_replay/api.py (52), cli.py (72); engine.py lines 1-700 swept (survivors pinned in PR 575), api/cli not.
6. B-S2-2-FOLLOW | spend-governor-bounds-rebase | after PR 566 and PR 555 land, rebase/merge PR 585 (api.py overlap on the two `note:` lines); only if a conflict shows. Not a new build.
7. B-575-GREEN | pr575-after-543 | PR 575 CI is red only on test_http_env_proxy_lint_c57 (known baseline, PR 543 fixes). After 543 merges, merge main into test/mutant-survivors-lane-r and confirm green. Not a new build.

Method notes for whoever claims 1-5: the mutator I used is a 60-line ast script (not in the repo); run per-service with a RELATIVE PYTHONPATH incl. sibling services' src (spend_governor is imported by claude-approver and attestation-reporter tests). Each mutant runs the service suite with -x: 13-20s per mutant for kill-switch/delegation-authority, so budget ~20 min per 60 mutants.

Not verified: that none of 1-5 is already claimed or covered by an open PR; the PR 575 survivor list is the only evidence.
