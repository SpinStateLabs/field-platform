# Reviewer report: PR 371 @ 13c91f546ea0c1d1fef67f94e4fe7264d5f3eda5 (C-635 / C-1144 / C-1086: agent-registry id grammar, manifest_ref containment, bounded content-keyed manifest resolver)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 05942b98; 14 commits incl. 1 merge of main; 13 files (+908/-22): field-core clients.py and validation.py, agent-registry api.py, cli.py, models.py, README, ENVIRONMENT.md, 6 test files. `git merge-tree --write-tree origin/main pr371` clean (HIGH). Author and committer of all 14 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH).

## Objections first
1. PROCESS: 8 of the 14 commits carry `Co-Authored-By: Claude Fable 5.1` (the other 6 Sonnet 5.5); the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailers are present; MEDIUM that a Fable session wrote them). Coordinator ruling needed; I did not and cannot rewrite history.
2. Security-sensitive change to a shared client (field-core ManifestResolver is read by sentinel, delegation, kill-switch, ledger retention): a resolver that now opens files with O_NONBLOCK, fstat, bounded read and sha256 cache can regress every reader at once.
3. Absolute manifest_refs stay unconfined by design (Don's ruling, option b, C-1144; api.py comment). Anyone who can register an agent can point at any readable absolute path; the PR narrows the oracle (one "missing" answer) but does not close it. Not a defect of this PR, a stated decision.
4. Base is 05942b98; main is 97dcfec1; clean merge, but field-core is shared so the coordinator's GX10 run on the rebased head matters more than usual.

## Verified
- Baseline on the exact head (relative PYTHONPATH, all services/*/src on path): the six new/changed test files 82 passed; whole packages/field-core/tests + services/agent-registry/tests 1915 passed, 1 skipped.
- Code read: id grammar (lower-case alphanumerics, single `.`/`_`/`-` separators, max 64) applies to new ids only, stored ids untouched (stated in the README); relative refs resolved and required to stay under the resolved FIELD_MANIFEST_DIR; failures answered "missing", no manifest_dir in the body; PATCH containment runs with the operator layer OFF too; resolver decides on the open descriptor, regular file only, cap 1 MiB, read bounded to cap+1, cache keyed on sha256 of the bytes it parses.

## Mutants (scratch worktree on the head; baseline 82 passed; kill = at least one failure in the six files)
| # | Mutant | Result | Killed |
|---|---|---|---|
| 1 | id max length 64 -> 65 | 1 failed | yes |
| 2 | id max length 64 -> 63 | 1 failed | yes |
| 3 | trailing separator allowed | 11 failed | yes |
| 4 | doubled separators allowed | 7 failed | yes |
| 5 | id validator disabled | 11 failed | yes |
| 6 | '.' dropped from separators | 3 failed | yes |
| 7 | absolute refs confined too | 4 failed | yes |
| 8 | relative containment removed | 9 failed | yes |
| 9 | containment lexical (no resolve) | 9 failed | yes |
| 10 | outside ref answered "invalid" | 3 failed | yes |
| 11 | absolute failure keeps its reason | 3 failed | yes |
| 12 | response includes manifest_dir | 3 failed | yes |
| 13 | PATCH containment removed | 1 failed | yes |
| 14 | PATCH containment only when mode != OFF | 1 failed | yes |
| 15 | NUL ref treated as absolute | 82 passed | NO |
| 16 | containment fails open on error | 9 failed | yes |
| 17 | size cap 1 -> 2 MiB | 2 failed | yes |
| 18 | size boundary `>` -> `>=` | 2 failed | yes |
| 19 | regular-file check removed | 4 failed | yes |
| 20 | O_NONBLOCK dropped | 2 failed | yes |
| 22 | stale cache (digest match always true) | 2 failed | yes |
| 23 | digest constant | 2 failed | yes |
| 24 | read chunk cap+1 -> cap | 1 failed | yes |
| 25 | oversize-after-read check removed | 1 failed | yes |
| 26 | parse re-reads the path, not the bytes | 2 failed | yes |
| 27 | NUL ValueError not caught as missing | 82 passed | NO (see below) |
| 28 | NotADirectoryError answered "invalid" | 82 passed | NO |
| 29 | non-regular answered "missing" not "invalid" | 7 failed | yes |
Totals counted from the table: 28 valid mutants (my mutant 21 did not build and is excluded), 25 killed by the six files, 3 survived (15, 27, 28). The 3 survivors run against the whole field-core + agent-registry suites (baseline 1915 passed, 1 skipped): 15 survives (1915 passed), 28 survives (1915 passed), 27 is KILLED by an older test, packages/field-core/tests/test_clients_resolve_manifest.py::test_a_ref_with_an_embedded_nul_is_missing_not_a_crash. So 2 true survivors: 15 and 28. I did not run the other suites that read manifests (sentinel, delegation, kill-switch, retention); the coordinator's 16-suite GX10 run covers them.

## Findings
- F-C635-1 PROCESS: Fable trailers (objection 1).
- F-C635-2 LOW: survivor 15, `_is_absolute` on a ref with an embedded NUL returns False; flipping it to True changes nothing any test sees (the ref is answered "missing" either way on the registered paths). Pin or simplify.
- F-C635-3 LOW: survivor 28, a ref whose parent component is a file (NotADirectoryError) is answered "missing" by design (no oracle) but nothing pins "missing" vs "invalid" for that case; add one test with `file.yaml/x.yaml`.
- F-C635-4 LOW: objection 3 stays an owner decision (absolute refs).

## Verdict: PASS WITH CONDITIONS on 13c91f546ea0c1d1fef67f94e4fe7264d5f3eda5
Conditions: (1) coordinator ruling on the Fable trailers; (2) CI green and a full 16-suite GX10 run on this exact head rebased on current main (field-core is shared; the resolver change affects every manifest reader); head frozen after this PASS, LOWs go in a NEW PR. Not run by me: CI, GX10, the other manifest-reading suites.
