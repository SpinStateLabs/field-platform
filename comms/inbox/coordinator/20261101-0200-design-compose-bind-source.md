# Design note: the compose bind-source checker (Lane 10)

Scope: tools/tests/test_compose_static_pins.py on main. Probes: probe1.py and probe2.py (scripts, scratch) and the runnable pytest 20261101-0310-design-compose-bind-probe-test.py (33 cases, all RED on main: 25 source strings, 8 whole documents); both import the checker unchanged, use made-up paths, and need only `pytest` and `pyyaml`. Baseline: the file's own suite is green (365 passed).

## 0. Correction to the framing
The last four findings were not four bugs but one design: the checker is a DENYLIST of host paths. A denylist over a space with unbounded spellings (variables, parents, symlinks, new credential tools) can only converge by luck. Each fix added items (`/var/lib` parents, HOME defaults, credential parents, PWD) and each reviewer found the next one outward. Confidence HIGH (test_compose_static_pins.py:98-122, reports C-424, C-434, C-441).

## 1. Objections to the current approach (at least three failure conditions)
1. Open-ended list: any credential or state directory not named passes (`.cache`, `.gitconfig`, `.bashrc`, `.local/bin`, `.config/systemd`, `.config/git`). New tools add new ones; the list is never complete. Probe1: 12 MISS in this class.
2. Spelling space: a `$VAR` / `${VAR}` / `${VAR:?}` with no default is "unknown" by design (test_compose_static_pins.py `_expand_defaults` docstring) and passes, including as a path PREFIX (`${X}/etc`). Probe2: red only for the literal spellings; `${X}`, `${X}/etc`, `${X:-/home/u}/.config` all pass in short AND long syntax.
3. Scope: the checker reads only `services.*.volumes` and top-level `volumes.*.driver_opts.device`. Other host-path-bearing keys are not read at all: top-level `secrets.*.file`, `configs.*.file`, `env_file`, `build.context`, `build.additional_contexts`, and `ipc: container:<x>` (probe2: 7 MISS). `include:` and `extends:` are not followed (file merge sees only the two named files).
4. Runtime vs text: what compose mounts is the RESOLVED path. Text analysis cannot see the estate `.env`, shell environment, or symlinks in a parent (a `./operators` that is a symlink to `/` is accepted). Failure condition HIGH: by construction static analysis cannot prove it.
5. Normalisation is lexical (`..` is resolved without the filesystem): correct for the compose engine only if no symlink is involved.

Steelman for the denylist: it is cheap, has no false positives on the estate's real binds, and every spelling is pinned by mutants. Its cost is the rising reviewer cycle, not the code.

## 2. The invariant (one paragraph)
A bind source may be exactly one of: (a) a RELATIVE path that stays inside the repository (the compose file's own tree up to the repository root, excluding `.git` and `.env*`); or (b) an ABSOLUTE path that is a descendant (never the root itself) of a root in an explicit ALLOWED_ROOTS set that the repository's own deploy documentation names for estate data (the caller-key and secrets directories). Everything else is forbidden: no variable may supply any part of a path that is not an allowed literal prefix; no source may name a host path the checker cannot resolve to a literal. A named volume has no host path, unless it carries `driver_opts` with `device`, which is then a bind and obeys the same rule.

## 3. The closed forbidden classes derived from the invariant
A source is forbidden iff any of these holds: F1 not literal after resolution (any unresolved variable, command substitution, empty); F2 absolute but outside ALLOWED_ROOTS; F3 equal to an allowed root (the root itself); F4 relative and escaping the repository, or naming `.git` / `.env*`; F5 `~`; F6 contains `..` that crosses out of its root; F7 contains a symlink anywhere (only checkable at runtime, section 5). Parents of credential directories fall under F2/F3 automatically: no list needed.

## 4. Spelling classes: handled / not handled (R = refused, P = passed)
| spelling | handled? | probe |
|---|---|---|
| absolute `/etc/x`, root, `//`, `/./`, `..` | R (HIGH) | probe1 |
| relative escape `../../../etc`, `~` | R | probe1 |
| `${V:-/}`, `${V-/}`, `${V:+/}`, nested default | R (default read) | probe1 |
| `${HOME}`, `$HOME` and four other settled names | R | probe1 |
| `${V}`, `$V` unknown | P: MISS (by design) | probe1 ROOTDIR |
| `${V:?m}` | P: MISS | probe1 |
| `${V}/etc` (variable prefix) | P: MISS | probe1, probe2 |
| `${V:-/home/u}/.config` (credential parent) | P: MISS (C-442 open) | probe2 |
| `/home/u/.config`, `.local`, `.local/share`, `.cache`, `.config/git`, `.gitconfig`, `.bashrc` | P: MISS | probe1 |
| `/mnt/x`, `/srv/x`, `/opt/x`, `/usr/bin`, `/var/log`, `/var/lib/foo`, `/lib/x`, `/tmp`, `/snap`, `/lib64`, `/lost+found` | P: MISS (below exact-forbidden dirs, "legal by design", C-391) | probe1 |
| `$PWD`, `$OLDPWD`, `$TMPDIR`, `$XDG_*`, `$SHELL` | P: MISS (PWD open C-442) | probe1 |
| upper-case `.SSH` (case-insensitive FS) | P: MISS (LOW; only on case-folding hosts, not Linux ext4) | probe1 |
| long syntax `type: bind` / `type: volume` with `source` | R | probe2 |
| top-level volume `driver_opts.device` (also `o: rbind`, nfs) | R for literal; P for `${X}/etc` and nfs | probe2 |
| `volumes_from` | R (the donor's volumes are read) | probe2 |
| `secrets.file`, `configs.file`, `env_file`, `build.context`, `additional_contexts` | P: MISS (never read) | probe2 |
| `ipc: container:x`, `network_mode: service:x` | P: MISS on ipc (LOW) | probe2 |
| symlinked parent | P: not detectable statically | n/a |
| merged files: `!override`, `!reset` | R/handled | existing tests |
| `include:`, `extends:` | not followed: MISS (MEDIUM, no probe: no such use on main) | n/a |
Confidence: HIGH for every row marked by a probe; MEDIUM for `include`/`extends` and the case-folding row (not run).

## 5. Recommendation: allowlist of permitted roots, plus a resolved-config check
Primary fix (cost low): replace the host-path denylist by the invariant in section 2. Implementation in Python: `ALLOWED_ABSOLUTE_ROOTS = {<one entry per directory the compose files bind today; derive from `grep -n 'volumes:' -A integration/demo/*.yml`>}`, relative sources must resolve under the repository, any `$` that survives default expansion is a failure. Keep the denylist as a second, redundant net (F-tests stay). Apply the same function to the five uncovered keys in section 4. Cost: (1) every new estate bind needs an entry in the allowlist (one line, reviewed); (2) the estate default for the caller-key directory sits under a user home directory, so that single root must be an allowlisted descendant, not the home dir; (3) an estate that overrides `FIELD_CALLER_KEYS_DIR` or similar in its `.env` can still point anywhere. That is a deploy-time concern: static text cannot close it.
Second fix (cost medium): at CI or deploy time, run the same predicate over the RESOLVED model (`docker compose config --format json`, which has every variable and merge applied), not the text. That closes all variable spellings, `include`/`extends` and merge order at once. Costs: needs the compose binary in CI (never on the estate host: `config` does not start containers but the rule is not to run compose there); a resolved path still can hit a symlink, so keep F7 as a runtime `realpath` check in the deploy script.
Recommended: both, in this order. Do not add further denylist entries to the current checker.

## 6. What a builder card should pin
For each row of the table marked MISS: one test that fails today; mutants: remove the allowlist, add a root, loosen F3.

## What I did NOT do
Did not run docker or compose. Did not edit the checker or any test. Did not probe symlinks, the estate `.env`, or `include`/`extends` (no such use on main). Did not verify real estate paths; the allowlist content must come from the compose files themselves. Did not merge or build a PR. Could not push (this note is delivered in chat for the coordinator).
