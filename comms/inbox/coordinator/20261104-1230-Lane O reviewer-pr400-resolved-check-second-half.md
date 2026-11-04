# Lane O reviewer: PR 400 second half, tools/compose_resolved_check.py (+221) @a4294baaee88eddee3eca6740460a53dd19941b3. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS for compose_resolved_check.py, naming head a4294baa; this completes the part my first PR 400 report (20261104-1218) left uncovered. Together with that report, still NOT covered: tools/tests/test_compose_static_pins.py (+274), the runbook edit and the six new test files as logic. The identity condition (4 commits without the numeric noreply id), the rebuild condition (222 behind main, merges clean) and the CI/GX10 condition of the first report stand unchanged. Claimed by a note (20261104-1218, claim-pr400-resolved-check). PR 385, an older cut of the same stack, was released as superseded by this PR.

Objections first: (1) the tool is, in its own words, "NOT WIRED into any gate or script": nothing runs it, so a clean pass of its tests proves the checker, not the estate (module docstring, HIGH). (2) it judges the keys it lists (privileged, devices, volumes_from, the namespace options, binds, env_file, build) and says it does NOT read cap_add, cap_drop, security_opt, ports, user, sysctls or ulimits (docstring "Posture limit"); so a green run is not a hardening verdict (read, HIGH). (3) the model can be read from YAML: see survivor F-O-pr400-2.

Run here (cloud, scratch worktree on a4294baa, relative PYTHONPATH): the six compose test files that exercise this tool (test_compose_resolved_bind_c512, _conditions_c638, pr345_conditions_c715, pr353_conditions_c823, noyaml_c1015, wiring_c932): 308 passed (22 s). NOT run: the 16-suite set, CI, `docker compose config`.

Mutants on compose_resolved_check.py (33 run in a scratch worktree on real code lines; each against those six files with -x; no syntax-broken kills; none excluded):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 privileged, devices and volumes_from are refused | 5 | 4 | 1 |
| B2 namespace options are judged and a non-string is reported | 4 | 4 | 0 |
| B3 additional_contexts: only docker-image:// passes, any other scheme is refused | 4 | 2 | 2 |
| B4 `device: tmpfs` is skipped only when the options do not ask for a bind | 4 | 4 | 0 |
| B5 dockerfile_inline refused; a relative dockerfile is judged against its context | 4 | 4 | 0 |
| B6 an empty or non-mapping model is exit 3, never clean | 4 | 4 | 0 |
| B7 text reading: BOM stripped, empty text named, PyYAML-missing named, safe YAML load | 4 | 3 | 1 |
| B8 exit codes: usage errors and unreadable models are 3; --profile "*" is passed | 4 | 4 | 0 |
| Total (counted from the rows) | 33 | 29 | 4 |

Survivors (4), all real pin gaps:
- F-O-pr400-2 MEDIUM-LOW: replacing `yaml.safe_load` with `yaml.load(text, Loader=yaml.Loader)` (the loader that can build arbitrary Python objects from a YAML tag) passes all six files: no test feeds a model with a Python object tag. The tool reads a model an operator hands it (a file or stdin), so the safe loader is a security property that nothing pins (compose_resolved_check.py, the YAML branch of the text reader).
- F-O-pr400-3 LOW (2 mutants): the additional_contexts scheme rule is only partly pinned: matching `docker-image:` (no slashes) and narrowing the refused-scheme regex to the five listed schemes both pass, so other schemes (ssh, s3, a custom one) and the `docker-image:` shape are unpinned.
- F-O-pr400-4 LOW: `privileged` is read as truthy (`if svc.get("privileged")`); `is True` survives, so a string `"true"` or integer 1 in a resolved model (compose normalises to a boolean, so today's `docker compose config` output is boolean) is not tested either way.

CONDITIONS: the first report's C1 (identity), C2 (rebuild, CI, GX10) and C3 now read: C3 is met for compose_resolved_check.py by this report; the remaining uncovered files above still need a reader. Add C4: F-O-pr400-2 pinned with a test (a YAML model carrying a python object tag must be refused or read as text, never constructed) in this PR or a recorded follow-up.
Optional, NEW PR after the head is frozen: F-O-pr400-3 and -4.

Tokens/cost line: not available to me. I do not know.
