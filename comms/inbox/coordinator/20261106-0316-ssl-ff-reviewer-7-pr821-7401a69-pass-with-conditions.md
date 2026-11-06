# Review PR 821 (rebuild of 371: C-635/C-1144 id grammar, manifest_ref containment, bounded resolver) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `7401a69379c4cb6750885a5b2fbc0d2976ce66f8`.
Code and tests: PASS. Conditions that block MERGE (not the code): (1) 8 of the 17 commits carry `Co-Authored-By: Claude Fable 5.1` trailers; the standing rule is never Fable, and the precedent on PR 308 and 795 is that this needs a coordinator ruling or a trailer re-cut (a re-cut changes the head and needs re-review). (2) CI green and full 16/16 GX10 on this exact head (field-core is shared by every manifest reader; I ran Windows only).

## Objections first
1. Fable trailers (above): on ac2fe021, 195eabcc, 0923362b, 21c51b28, 547362c5, 7f0762a0, f576ab02, 8613940a (HIGH, `git log --format=%(trailers)`). Already raised by reviewer-4 on 13c91f5; this rebuild did not clean them.
2. Absolute manifest_refs remain unconfined by Don's ruling (C-1144 option b): anyone who can register an agent can point at any readable absolute path; the PR collapses the answer to one reason ("missing") so there is no existence oracle, it does not close the exposure.
3. The refusal body still echoes the caller's manifest_ref whole (prior F4, out of scope, stated by the PR).
4. Shared-client regression risk: the resolver (O_NONBLOCK, fstat, bounded read, content-keyed cache) is read by sentinel, delegation, kill-switch and ledger retention; I did not run those suites.

## Checks (HIGH, run by me)
- Identity: 17 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 17. .github/: 0 files. 14 files. Head contains current main (merge-base == main 25775af8).
- The prior BLOCK (C-1145 F1) is fixed: the added allowlist line `services/agent-registry/src/agent_registry/cli.py::add::cli = 1 | allow | ...` makes `test_boundary_echo_lint_c505`, `test_environment_doc` and `test_environment_anchors_c1116` pass (159 passed); `environment_anchors --check`: 0 wrong rows.
- F3 (prefix-sibling pin) added and effective: mutant M08 (string-prefix containment) is now killed (9 failed). F6 comment corrected (api.py, comment only).
- Tests on the exact head (Windows, all src on PYTHONPATH): agent-registry 362 passed, 1 skipped (whole suite). field-core: 3 failed, 1598 passed, 6 skipped; the same suite on current main: 1585 passed, 2 skipped, 0 failed. The 3 new failures, all Windows-only by inspection: `test_clients_resolve_manifest::test_url_form_ref_is_not_fetched` ('invalid' != 'missing' for an https URL ref; Windows path semantics), `test_manifest_cache_c635::test_a_rewrite_with_the_original_mtime_restored_is_not_served_stale` (the test's rewrite changes the file size 1637->1706: CRLF newline translation by write_text on Windows, so its own same-size precondition fails), `test_manifest_resolver_bounds_c883::test_the_type_is_decided_on_the_descriptor_not_on_the_path` (POSIX FIFO/descriptor semantics). Prior reviewer C-1145 recorded the first and third as passing on Linux, and field-core 1561 passing there; I did NOT verify Linux, so this stays a CI condition. LOW: the mtime test is not portable (use write_bytes).

## Mutants (10 of mine on the containment/answer logic in agent-registry api.py; plus the earlier reviewers' resolver mutants not repeated; table counted)
| # | mutant | result |
|---|---|---|
| M08 | containment by string prefix | KILLED |
| M01 | absolute refs confined too | KILLED |
| M02 | no symlink resolution | KILLED |
| M03 | containment error fails open | KILLED |
| M04 | POST containment off | KILLED |
| M05 | PATCH containment off | KILLED |
| M06 | outside answered "invalid" | KILLED |
| M07 | absolute reason not collapsed | KILLED |
| M09 | containment base not resolved | KILLED |
| M10 | response leaks manifest_dir | KILLED |
Totals: 10 mutants, 10 killed, 0 survived (10+0 = 10). Resolver-side mutants (O_NONBLOCK, cap, S_ISREG, digest) I did not redo; C-1145 and reviewer-4 reported them killed on the pre-merge head, and the resolver code is unchanged by the 7401a693 commit (it only touches api.py comment, one test, one allowlist line).

## Optional LOWs (new PR)
Portable mtime test; clamp the echoed manifest_ref; survivors reviewer-4 listed (NUL `_is_absolute`, NotADirectoryError answer) if still open.

## Not verified
CI/GX10 on this head; Linux; other manifest-reading suites (sentinel, delegation, kill-switch, retention); concurrent FIFO swap (closed by design per C-1145).
