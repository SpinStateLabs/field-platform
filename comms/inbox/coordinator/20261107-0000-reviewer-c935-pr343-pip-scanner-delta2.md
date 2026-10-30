# C-935 reviewer report (Lane 5): PR 343 @30015c3 (delta on 1f93620; C-730 conditions F-C730-1..6), CI pip-pin scanner

VERDICT: PASS WITH CONDITIONS on 30015c37f0f7137f38e3bfceffa155d048e49beb. The delta (one commit, builder Lane 1, author Don Hagell noreply; tools/tests/test_ci_pip_pins_c23.py +216/-25 and 3 lines in tools/tests/test_yaml_duplicate_keys.py; no workflow file changed) closes all six C-730 findings for every spelling I listed: 39 of my 40 earlier run-text bypasses are now red, and the 40th (`. ./file` redefines C) is named in the header. 5 of the 10 earlier surviving mutants now die; 4 of the other 5 are equivalent (they can only make the scanner stricter or change nothing); 1 is real and LOW. My new probes find a NEW same-class gap. A `$C` definition that bash never applies still arms the rule: the definition behind `false &&`, `[[ .. ]] &&` or `true ||`, sent to the background with `&`, put in a pipeline element, or blanked by `trap 'unset C' DEBUG`. I checked all six in bash. Other new gaps: a composite-action step with `shell: python` (not read at all); a python shell given by path or pypy; `alias pip=...` with expand_aliases; PIP_* names built at runtime and written to GITHUB_ENV; pip config files located via XDG_CONFIG_HOME or a venv. Each is a new spelling, not a C-730 listed one, so the C-643/C-730 acceptance is met. The scanner passes the shipped ci.yml on the head and on current main 5777030 (whose .github/ is byte-identical to base 5808a5c). The head merges clean. The whole tools suite is green on the GX10 and GitHub CI is green on the head. Merging is a strict tightening and safe. Class and file:line only.

OBJECTIONS FIRST
1. F-C935-1 MEDIUM (PROVEN, run and bash-checked): `$C` is armed by statement TEXT (`st == C_DEFINITION`, test_ci_pip_pins_c23.py:366-368) even when the statement is the right side of `&&`/`||`, ends in `&`, or is a pipeline element. The splitter (:206-235) throws away the separator, so the scanner cannot know the define is conditional or runs in a subshell. Bypasses (scanner returns [], C empty in bash): `false && C="..."`, `[[ -n "$X" ]] && C="..."`, `true || C="..."`, `C="..." &`, `C="..." | cat`, each followed by `pip install $C requests`. Also `trap 'unset C' DEBUG`: the disarm rule (:369-371) only looks at `ws[0]` in unset/read/declare/typeset, and the DEBUG trap unsets C before the install (checked: `[]`). The header (:160) says a define arms only "before any if/for/while/case/function/heredoc statement", which is true, but these forms are not named. [HIGH, run]
2. F-C935-2 LOW-MEDIUM (PROVEN): `shell_problems` (:324-339) reads workflow defaults, job defaults and job steps, but NOT composite-action steps (`runs.steps`). A `.github/actions/x/action.yml` step with `shell: python` and `subprocess.run(["pip","install","requests"])` passes. The header (:165-166) says "a python `shell:` (step or defaults) is refused". The test `py()` is `startswith("python")`, so `shell: /usr/bin/python3 {0}`, `shell: pypy3 {0}` and `shell: ${{ matrix.sh }}` also pass. [HIGH, run]
3. F-C935-3 LOW-MEDIUM (PROVEN): names and config the text scan cannot see, not named in the header (:168-177):
   - an index name built at runtime and written to `$GITHUB_ENV` for the NEXT step: `"PI""P_INDEX_URL=..."`, `${v^^}` of a lower-case name, `${P}_INDEX_URL` (PIP_ENV :200 needs the literal upper-case name);
   - `shopt -s expand_aliases; alias pip='pip --index-url=...'`, after which `pip install $C x` passes (checked in bash: the alias applies);
   - `hash -p ./fake pip` or a PATH prepend;
   - a pip config the workflow never names: `XDG_CONFIG_HOME` pointing at a repo directory (checked: `pip config list` reads the index from it), a venv-site `pip.conf` copied by `cp -r`, or a file name split by quotes (`pip.con""f` beats :358).
   The header names `eval "$X"` and "a runner image whose global pip.conf differs" but not these. [HIGH, run]
4. F-C935-4 LOW (PROVEN by mutant): four real survivors:
   - A07: the non-install-verb branch removed (:386-388). `pip download $C x`, `pip wheel $C x` and `pip config set ... $C` with C defined then pass. This is the earlier M37, still alive; the PR body says all of my earlier survivors are killed.
   - A11 and A13: constraint values (:399) or build constraints (:400) taken from quote-stripped words. Each passes one half-quoted form (`--log "-c a.txt" --build-constraint b.txt`, or the mirror). The only quoted-inline test quotes both halves, so it pins the pair, not each half.
   - A19: `{` no longer nests (:372). `{` + define + `} > /dev/null &` then passes. The dead-function test also matches `()`.
   [HIGH, run]
5. F-C935-5 LOW: false positives. The earlier 3 of 15 are unchanged (`uv sync --frozen`, `echo "run pip install x"`, `pip config list`). Three new, all fail-closed:
   - a correct define placed after any `for`/`if` (design: the `nested` flag never resets);
   - `pip install $C --upgrade-strategy only-if-needed` (`--upgrade\b` matches);
   - `echo "PIP_INDEX_URL is not set"`.
   None occurs in ci.yml. [HIGH, run]
6. PR body claims that are not exactly true:
   - "49 checker mutants ... plus the reviewer's survivors: all killed". M37 (= A07) survives; M39, M44, M21 and M36 survive as equivalents.
   - "Whole pytest tools ... 3276 passed, 6 skipped". My count on the GX10 venv is 3278 passed, 4 skipped. That is a different venv, so not a contradiction of a green result.
   All other body claims checked hold: 163 tests in the pip file (collected); the duplicate-key lint globs `.github/actions`; the header names $C proves flags, not coverage. [HIGH, run]

ASSUMPTIONS
1. Head 30015c3 = bec36bc + 1f93620 + 30015c3 on base 5808a5c. origin/main is 5777030 and has no change to `.github/`, this test or the dup-key test since base (git diff --stat empty). `.github/` holds only workflows/ci.yml on head and main (no `.github/actions/`). [HIGH, git]
2. "BYPASS" = `workflow_problems(shipped + one extra workflow built with the file's own _body())` returns []. A "listed" spelling is one in my C-730 report. Mutants are exact-string replacements with a count==1 check before applying (no silent no-ops: one anchor that matched twice was fixed), judged by the PR's tests (`pytest -x` on the PR file, or the dup-key file for its own mutant). Files restored and verified byte-identical. [HIGH]
3. Bash semantics were checked with bash 5 on the GX10 (`&&`/`||`/`&`/`|` define, DEBUG trap, alias), and pip config resolution with pip 24.0 (`pip config list`; no install made). GitHub runner equivalence is assumed, not run. [HIGH for the scanner answers, MEDIUM for runner equivalence]

REASONING
1. C-730 closure, per finding (probe = earlier bypass re-run on the head; mutant = the rule removed, judged by the PR's tests):
   F-C730-1 FIXED. `;`, `|` and `--constraint` mutants A01, A02, A04 KILLED. Probes `pip install requests; echo $C` and `| tee $C` caught. Composite env mutant A05 KILLED.
   F-C730-2 FIXED. P03 `--log '$C'`, P03b quoted inline constraints and P37 folded define-then-use all caught. A12 ($C from quoted words), A14 and A50 (bare_words not opaque) KILLED. Partly pinned: A11 and A13 survive (objection 4).
   F-C730-3 FIXED for every listed spelling.
     - Probes caught: P01 `)#`, P02 single `&`, P10 dead if, P11 heredoc, P12 uncalled function, P13 `C[0]=`, P14 `printf -v C`, plus mapfile (PR test).
     - Mutants KILLED: A03, A10, A15-A18, A20-A22. A06 (backslash in double quotes, earlier M34) KILLED.
     - New same-class gap: objection 1.
   F-C730-4 FIXED for every listed spelling.
     - Probes caught: P15 printf -v PIP_*, P16 GITHUB_ENV quoted `=`, P17 the `<<` form, P18 UV_INDEX_URL, P34 pwsh `$env:`, P19 `--find-l=`, P20 `--no-build-iso`, P22b `--requiremen`.
     - Container env, non-mapping env and lower-case env keys are pinned by PR tests.
     - Mutants KILLED: A23-A29, A52, A60.
     - New gaps: objection 3.
   F-C730-5 FIXED or NAMED.
     - Probes caught: P04-P09, P23-P33.
     - Python `shell:` on a step, job defaults or workflow defaults is pinned.
     - Mutants KILLED: A30-A46.
     - P35 (sourced file) is named in the header.
     - Residual gaps: objections 2 and 3.
   F-C730-6 FIXED. test_yaml_duplicate_keys.py:72 globs `.github/actions/**/action.y{a,}ml`, and the discovery test covers both. Mutant A51 (glob removed) KILLED. The scanner still uses `yaml.safe_load` (:291, :307, :330), declared in the header (:175-176). Strict load (`load_strict`) of ci.yml passes on the head and on main. [HIGH, run]
2. Earlier 10 survivors re-created:
   - KILLED 5: M05 `;` (A01), M06 `|` (A02), M07 `--constraint` (A04), M30 composite env (A05), M34 backslash in dq (A06).
   - SURVIVE 5:
     - M37 (A07): real, LOW, objection 4.
     - M39 (A08, `-U pip==` branch): equivalent, because the short-flag refusal still flags it.
     - M44 (A09, `-c` exemption): equivalent for spaced forms.
     - M21 (A65, `$(` in words): equivalent, since `(` is already blanked.
     - M36 (A66, `--` in the short test): equivalent, since `-[A-Za-z]*[Uifr]` cannot match `--`.
   [HIGH, run]
3. Checker mutants: 66 hand mutants in total (64 in one batch plus A65 and A66).
   - KILLED 56.
   - SURVIVED 10:
     - A07, A11, A13, A19: real, objection 4.
     - A47 (shell value not lower-cased): LOW, `shell: Python`.
     - A08, A09, A49 (`&>` and `>&` redirect branch, which only adds false positives), A65, A66: equivalent, or they move only toward fail-closed.
   [HIGH, run]
4. Probes on the head:
   - 40 earlier run-text probes: 39 caught, 1 documented (P35).
   - 23 new run-text probes: 17 BYPASS, but 3 of those are controls that are not bypasses (a constrained install, `set --`, `env -i`) and N17 (IFS=:) fails closed in pip (checked: pip errors on the single-word constraint path). That leaves 13 real: objections 1 and 3, plus N14 `-c /dev/stdin` (content class, named in the header as "constraint files whose CONTENT is not an exact pin").
   - 5 YAML probes: Y01-Y04 BYPASS (objection 2), Y05 (python heredoc with subprocess) named in the header.
   - 20 legitimate lines: 14 accepted, 6 refused (objection 5).
   [HIGH, run]
5. Shipped workflows: `workflow_problems(shipped_workflows())` == [] on the head, and == [] with `shipped_workflows(root=<main 5777030 .github extract>)` (only ci.yml discovered). [HIGH, run]
6. Suites:
   - PR file alone: 163 tests collected; with the dup-key file, 224 passed in the mutant worktree before and after mutation.
   - Whole tools suite on the head: `python -m pytest -q tools/tests`, PYTHONPATH from the worktree's `packages/*/src` and `services/*/src`, venv-fieldrev, Python 3.12. Result: 3278 passed, 4 skipped, 0 failed, 500.9 s, EXIT=0. Load was under 2 at start.
   - GitHub CI on the head: tests 3.11, 3.12, 3.13 and 3.14, compose-smoke, compose-upgrade-smoke and fly-image-smoke all SUCCESS (as read with `gh pr view`).
   - The head merges clean onto main 5777030 (`git merge-tree`).
   [HIGH, run; CI as read]

CONCLUSION
PASS WITH CONDITIONS on 30015c37f0f7137f38e3bfceffa155d048e49beb. Every C-730 finding is fixed or declared out of scope in the header. Safe to merge as a strict tightening. The conditions are follow-up work (builder, tools/tests/test_ci_pip_pins_c23.py only) and need not block the merge:
P1 MEDIUM: arm `$C` only when the define statement stands alone between newlines or `;`. Refuse, or do not arm, a define joined by `&&`, `||`, `&` or `|`, which means keeping the separator in `statements()`. Disarm on any `trap` that names C. Pin N01-N06.
P2 LOW-MEDIUM: read `shell:` on composite-action steps. Replace `startswith("python")` with an allowlist (bash, sh, pwsh, powershell, cmd, with or without `{0}`), refusing anything else, including an expression. Pin Y01-Y04.
P3 LOW: refuse writes to `$GITHUB_ENV`/`$GITHUB_PATH` whose name part is not a literal (`$`, quotes or `}` before `=`), `alias pip`, `hash -p`, `XDG_CONFIG_HOME`, and `cp -r` into a venv; or NAME each in the header.
P4 LOW: kill A07 (`pip download $C x` with C defined is refused), A11 and A13 (one test per half-quoted inline form), and A19 (a `{` group case with no `()`). Correct the PR body's "all killed".

What I did NOT do: run the workflow on GitHub or `act` (only read the CI result); test Windows cmd or pwsh beyond one `$env:` spelling; run uv, poetry, conda or a real network install (pip only `config list` and a missing-file dry run); probe the other-repo `uses:` and reusable-workflow classes (named in the header); edit, push, comment on or merge anything; touch the shared checkout beyond `git show`/`git diff`/`git fetch`/`gh pr view`/`gh api`.
GX10 artefacts:
- worktrees ~/ff-work/wt-lane5-pr343e and ~/ff-work/wt-lane5-pr343e-mut (the mutant file is restored and clean at 30015c3);
- ref refs/l5-c935/pr343 in the c326 clone;
- scratch ~/ff-work/l5-c935-* (scripts, logs, the main .github extract, the XDG test dir).
No docker. Load was checked before the suite.
