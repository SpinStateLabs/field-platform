VERDICT: C-698 FAIL (non-blocking for merge, contract not met) on 783a85fa9d32818ead55853bc20cda41d77142c2 (PR 353). The "never 1, no traceback" exit contract (tools/compose_resolved_check.py:36-38) is broken by an invalid-UTF-8 model and by a non-default sys.path; a non-string bind source passes as clean. UNVERIFIED on any estate; cloud container, no docker run, no GX10.

Note on the card text: the contract in the docstring is 0 clean, 2 refused, 3 could not check; "0/1/2" in the card reads as 0/2/3 with 1 forbidden. I judged against the docstring.

## Objections first
1. UNREADABLE TEXT EXITS 1 WITH A TRACEBACK. The read block (compose_resolved_check.py:200-207) catches OSError, RuntimeError, yaml.YAMLError, SubprocessError. `open(..., encoding="utf-8").read()` and `sys.stdin.read()` raise UnicodeDecodeError, a ValueError, which is none of those. Probe: a file whose bytes are 0xff 0xfe 0x00 'bad' gives rc=1 and a traceback, with and without --realpath. A CI step that treats 1 as "tool broke" and 2 as "refused" cannot tell this from a crash. HIGH (observed).
2. A NON-STRING BIND SOURCE IS ACCEPTED AS CLEAN. `source_problem` returns None for any non-str (compose_resolved_check.py:82-83, comment "a sourceless volume"). `check_model` calls it for every `type: bind` entry that has a `source` key (line ~143). Probe: `type: bind, source: 5` (also a list, null, true) gives rc=0 "every bind source is allowed". The C-638 change added shape errors for `volumes` and `build` but not for the source value, so the new "unknown shape is 3" rule has a hole exactly where the allowlist decides. compose itself would not emit this, so this is fail-open on a malformed model, not on a real one. MEDIUM.
3. "SHAPE NOT KNOWN" IS NOT UNIFORMLY 3. A model that is a list, empty, `services: 5`, or a cyclic alias exits 2 "REFUSED the model has no services" (probe), while `volumes: "x"` or `build: 7` exits 3. Both are "a model whose shape it does not know"; the docstring puts that in 3. Callers cannot separate "a source is refused" from "this was not a compose model". MEDIUM (observed).
4. THE SIBLING IMPORT BREAKS UNDER SAFE-PATH MODES. `from compose_bind_rules import ...` (line 51) resolves only when the script directory is on sys.path. With `python -I`, `-P` or PYTHONSAFEPATH=1 the tool dies with ModuleNotFoundError, rc=1, traceback (probe). Usage text uses plain `python tools/...`, so the documented call works; a hardened wrapper would not. LOW.
5. THE ROOT IS TRUSTED AS GIVEN. With --realpath the root is resolved (line 211, the C-585 F-1 fix: verified, a symlinked checkout root is accepted, and the same root without --realpath is refused by spelling). Nothing checks that the root is a checkout: `--repo-root /tmp` allows every source under /tmp, with and without --realpath (probe). A root of "/" refuses everything (fail-closed: normal("/") + "/" gives "//"). So a root resolving outside the repository is only as safe as the operator who passes it. MEDIUM.
6. `--help` exits 0, which reads as "clean". argparse's own help exit is not routed through `_Parser.error`. LOW.

## Steelman
Items 1, 2, 4 and 6 need a malformed or hostile input to a tool the operator runs on their own machine; real `docker compose config` output is valid UTF-8, strings and a known shape. The PR's own 37 tests pass (observed). Usage errors are 3, a missing file is 3, a docker failure is 3, in-repo and symlinked-root cases behave as documented, and symlink escapes are refused under --realpath and documented as spelling-only without it.

## Probe table (made-up inputs, throwaway directory; script pushed beside this note)
| Input | rc | Note |
|---|---|---|
| invalid UTF-8 file, with or without --realpath | 1 | traceback |
| `source: 5` on a bind volume | 0 | allowed |
| `services: 5`, `[]`, empty file, YAML alias cycle | 2 | "no services" |
| `volumes: "x"`, `build: 7` | 3 | shape message |
| missing file, no args, unknown flag, missing --repo-root | 3 | |
| in-repo source | 0 | |
| source through a symlinked in-repo dir to the system config directory, no --realpath | 0 | spelling only, documented |
| same with --realpath | 2 | on the denylist |
| symlinked root + --realpath | 0 | root resolved |
| symlinked root, no --realpath | 2 | spelling |
| PYTHONSAFEPATH=1 | 1 | traceback |
| `--help` | 0 | |
HIGH on each (observed).

## Recommended structural fix
Wrap the whole of `main` after argument parsing in one `try/except Exception -> 3` (including the read), catch UnicodeDecodeError explicitly, make `source_problem` return a reason for a non-str source when the entry is `type: bind`, make "no services" exit 3, and put the tools directory on sys.path explicitly (or import by path) so safe-path modes work. Add one test per exit code that runs the script as a subprocess.

## What I did NOT do
- No `--run-compose`: I never run docker. The RuntimeError path to 3 was seen only with a missing file name.
- No junction test (Windows): not available here. Windows junction behaviour of os.path.realpath is not in source for me. LOW confidence it matches POSIX symlink handling.
- No GX10 run. No review of compose_bind_rules.py beyond what the tool imports.
- Did not check that the test file pins items 1-6 as survivors.
