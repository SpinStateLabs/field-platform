# Builder Lane 1: correction, my later commits on PRs 291 and 295 never reached main; replacement PRs coming

ERROR (mine): I kept pushing follow-up commits to the branches of PRs 291 and 295 after those PRs had merged at their first commits (main 61000ba = c13f2de, main 9e6627f = b47ee05). Main does NOT contain 999bfd4, e39671e or 6dd592e (PR 295 branch), nor c3dd32f (PR 291 branch). Cards C-476 and C-486 show REVIEW at e39671e: that review applies to a branch that is not going to merge as is. I should have checked main after each merge note.
FIX, in progress:
1. C-476 + C-486 (lint follow-ups plus the lifecycle-manager `PerRequestAuthClient` constructor): rebuilt as ONE commit on current main a9dc4f3, branch `test/http-env-proxy-lint-c57-r2`, local head 4da4a26: lint file 65 passed, lifecycle-manager suite 227 passed, allowlist unchanged (58 keys / 63 sites). The whole tools suite is running; I push and open the draft PR when it is green and send the head SHA. The reviewer verdicts on e39671e carry over only by content (same diff, rebased clean, no conflict).
2. C-459: PR 309 (another builder) already carries the build-constraints; my c3dd32f duplicates it, I drop mine. Its pins match mine (hatchling 1.33.0, editables 0.6, same closure) which is an independent cross-check.
3. C-460 (the pin test over every workflow, job and step; 34 tests, 28 checker mutants red) stays mine: I will rebase it on main AFTER PR 309 merges (same test file) and open its own PR. Please keep C-460 open for me.
Blockers: none. The forks for C-456 and C-457 are still running.
