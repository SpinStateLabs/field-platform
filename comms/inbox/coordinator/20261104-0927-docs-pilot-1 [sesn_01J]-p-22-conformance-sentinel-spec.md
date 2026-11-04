CORRECTION FIRST: the card premise holds on main cd3b76901f9aabfd45cee546f597177b8739d6ea (SPEC.md:26 says "15 tests"; SPEC.md:25 lists only check|clauses|serve). One deviation: the card says "fix", but the docs role is addition-only outside the FALLBACK, so SPEC.md lines 25-26 were NOT rewritten. A dated Corrections section was appended instead. An in-place edit of those two lines needs a coordinator exception.

Item: B-P-22 / P-22. Card: conformance-sentinel SPEC.md says '15 tests' (SPEC.md:26) and omits score/version in the CLI line; fix without a copied count, check README.md too; verify scout evidence on current main first.
Branch docs/p-22-conformance-sentinel-spec, head 791c42f678248f7e303aed1b5dcc73607ba80d1a, draft PR #531.

ASSUMPTIONS
1. origin/main = cd3b76901f9aabfd45cee546f597177b8739d6ea fetched this session.
2. Docs role rule (addition-only) overrides the word "fix" in the card.
3. The pinning tests (tools/tests, ENVIRONMENT.md anchors) do not touch these files.

OBJECTIONS / FAILURE CONDITIONS
- Already documented? No: README CLI block lacks version/self-manifest/score; SPEC has none of them in the CLI line.
- Wrong if: (a) a command in cli.py is later renamed or removed; (b) the test count is later made to match 15 again (the entry says only "not the current count" at this SHA, so it would then be stale); (c) typer registers commands differently than the decorators read (not run here, read from source only); (d) the SPEC line numbers shift (cites carry the SHA).
- Not checked: the named adversarial tests exist (stated in the entry as not re-checked).

REASONING
1. cli.py on main has decorators at lines 28 (version), 33 (check), 59 (self-manifest), 91 (clauses), 98 (score), 203 (serve) [HIGH]. Exit 0/2/1 only on check (cli.py:40,53-56); score 0/3 (cli.py:115) [HIGH].
2. Test functions: `git grep -h -c -E '^\s*(async )?def test_' ... | awk sum` = 144 test functions across 15 files (a def count, not a pytest collected count; parametrization not counted). 15 matches the number of FILES, not tests: probable origin of the error [MEDIUM]. The 144 is NOT written into the docs.
3. README block lines 187-191 lacked the three commands; README.md:136 and :162 mention self-manifest and score elsewhere [HIGH].
4. Edits: SPEC.md +25/-0 (new Corrections section), README.md +10/-0.

CITES: 12 FOUND, 0 NOT FOUND (awk count over $S/cites.tsv: "FOUND 12").

GATES
1. docs-only: git diff --name-only -> services/conformance-sentinel/README.md, services/conformance-sentinel/SPEC.md.
2. addition-only: numstat "10 0 README.md", "25 0 SPEC.md".
3. public scan: 5 hits, all benign (context lines `--token-id T`, `@governed` heading, phrase "token narrower than manifest").
4. pinning tests: `git grep -l ENVIRONMENT.md -- tools` -> tools/environment_anchors.py, tools/tests/test_ci_anchors_step_c1191.py, test_environment_anchors_c1116.py, test_environment_doc.py. None reference the sentinel README/SPEC (git grep found none). NOT run. UNVERIFIED against the GX10.

NOT VERIFIED: pytest was not run (no venv, no GX10); `pytest --collect-only` count not obtained; typer command registration not executed.
Usage not in source.

CONCLUSION: PR #531 (draft) appends a dated correction to SPEC.md and completes the README CLI block. Reviewer should decide whether to allow an in-place edit of SPEC.md lines 25-26. Note: `level` showed reviewer unclaimed=0 RESTOCK at claim time.
