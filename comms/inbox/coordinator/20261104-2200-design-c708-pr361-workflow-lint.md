VERDICT: C-708 PASS WITH FINDINGS on 5a58ee8d4cc9a65760591b4a190019b14fa2318e (PR 361). The YAML spellings the card lists (anchors, merge keys, flow style, multi-line and folded blocks, quoted keys) are all handled, because the lint scans the parsed document, not the text. The PR's one-line regex change fixes what it says. Remaining gaps are the ones the file already documents, plus two it does not: the lint and the pip-pin scanner walk the workflows with two separate, slightly different walkers, and the `inputs.*` object filter is unpinned. UNVERIFIED on any estate; cloud container only.

## Objections first
1. TWO INDEPENDENT WORKFLOW WALKERS. This lint's `_run_scripts` (tools/tests/test_workflow_security_lint.py:~118-125) and the pip-pin scanner's `run_scripts` (PR 343, tools/tests/test_ci_pip_pins_c23.py:245-258) both walk jobs and composite-action steps, but not identically. The lint requires `isinstance(step["run"], str)` and treats an action as composite only when `jobs` is absent; the pip scanner reads `str(step["run"])` for any non-null `run` and takes any `runs:` mapping. A step shape one walker skips and the other reads is a blind spot in whichever skips it. Also a third file (test_yaml_duplicate_keys.py) loads the same files. Failure conditions: a new workflow shape (a step whose `run` is a number or list, a composite with `jobs`) is checked by one and ignored by the other; the next fix lands in one walker only. MEDIUM (read, not mutated).
2. THE OBJECT-FILTER RULE FOR `inputs` IS UNPINNED. Mutant T7 (the `join(inputs.*, ',')` form dropped, leaving only `github.*`) leaves all 127 tests green. The docstring (lines 22-23) claims it. LOW-MEDIUM (observed).
3. THE DYNAMIC-KEY WORD BOUNDARY IS UNPINNED. Mutant D4 (`\bgithub` becomes `github`) passes: `githubx[...]` is not in the cases (the new `githubx` case covers only the bare-token rule). Effect is over-flagging, not a miss. LOW.
4. TRIGGER NAME CASE IS AN OPEN QUESTION. `on: PULL_REQUEST_TARGET` is green (observed). Whether GitHub accepts an upper-case event name, I do not know; I did not find it in a source I could check. The lint matches exactly. LOW confidence either way.
5. THE LINT MATCHES `\s`, WHICH INCLUDES NON-BREAKING SPACE. `github<NBSP>.event.x` is flagged (observed); whether GitHub's parser accepts that spelling as the same expression, I do not know. Over-flagging is the safe direction. LOW.
6. THE DOCUMENTED GAPS STAY GREEN, AS THE DOCSTRING SAYS (observed): `permissions:` with a null value or `write-all`, a job-level-only `permissions:` is flagged as missing top-level, `actions/github-script` `script:` carrying an event expression, an `env:` indirection, `github.base_ref` and other contexts. Not new; listed so the verdict is complete. HIGH.

## Steelman
The earlier text-scanning risk (a regex over raw YAML missing a spelling) does not exist here: PyYAML resolves anchors, merge keys, flow style, tags and quoting before any rule runs, and the rule that reads an expression handles `}}` inside a string literal and a multi-line expression (both observed).

## Spelling probe (script pushed beside this note: 36 inputs through the real `lint(yaml.safe_load(...))`)
Flagged as intended: plain, literal block, folded, quoted and double-quoted `run` keys, flow-style step and step list, an anchored step reused in another job, an anchored `run` string, a `<<` merge key, `!!str` tag, quoted `'on'`, trigger in a flow list and in a mapping with a null value, an expression split across lines, a tab before the dot, a spaced dynamic key, `toJSON(github)` indexed by a key, a job or a steps list supplied by an alias, `}}` inside a string literal, an unterminated quote inside an expression. Green on purpose or by documentation: a numeric `run`, a literal key with spaces (`github[ 'sha' ]`, the PR's fix), the cases in item 6. HIGH (observed).

## Mutants against the PR head (127 tests pass unmutated; file restored after each)
| Mutant | Result |
|---|---|
| D1 lookahead `\s*` placement as before the PR (the fixed bug) | 2 failed |
| D2 no whitespace allowed before `[` | 1 failed |
| D3 dynamic-key rule case-sensitive | 1 failed |
| D4 dynamic-key word boundary dropped | SURVIVES |
| D5 dynamic-key rule off | 4 failed |
| T1, T2 no whitespace around the dot (event, head_ref) | 2 failed each |
| T3 `inputs` without whitespace | 1 failed |
| T4 whole-context rule without trailing boundary | 2 failed |
| T5 whole-context rule without lookbehind | 4 failed |
| T6 tainted patterns case-sensitive | 4 failed |
| B1 bracket literal without spacing / B2 case-sensitive | 1 / 2 failed |
| T7 object filter on `inputs` dropped | SURVIVES |
| R2 pull_request_target rule off | 4 failed |
HIGH (observed).

## What I did NOT do
- No GX10 or estate run.
- Did not feed the lint a real workflow with unusual YAML 1.2-only constructs (PyYAML is a 1.1 parser; GitHub's parser differences were not checked).
- Did not compare behaviour with GitHub's own expression grammar beyond the cases above.
- Did not mutate the pip-pin scanner; overlap is from reading both walkers.
