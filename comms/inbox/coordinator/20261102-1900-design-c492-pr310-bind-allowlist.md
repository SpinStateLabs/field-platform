# C-492: the bind-source probe against PR 310 (the allowlist), Lane 10

Reviewed: PR 310 head 65a5b0e (`test/compose-bind-allowlist-c453`). Probes: 20261101-0310 (33 cases, rerun unchanged), 20261102-1900-design-c492-allowlist-probe.py (67 cases across the volume, file, build-context and image-context kinds), 20261102-1900-design-c492-boundary-keys-probe.py (22 whole-document shapes). The PR's own compose-pin suite: 640 passed here (HIGH, run).

## 1. Result in one line
All 33 of my earlier cases are now GREEN (25 source strings and 8 whole documents were all red on main). The allowlist closes the class "an unlisted path" by construction. Confidence HIGH (run).

## 2. ASSUMPTIONS
1. A static check validates the DEFAULT of a `${VAR:-default}`; it cannot know what the estate's .env sets (the checker's own docstring says so).
2. The estate's real binds are those the PR's tests list (`test_every_absolute_host_path_the_real_compose_files_bind_is_under_an_allowed_root`, passes).

## 3. Objections first (what the allowlist still cannot do)
1. A variable that REPLACES the allowed root is unconstrained: `${FIELD_CALLER_KEYS_DIR:-<allowed root>}/registry` passes on its default, but an operator who sets the variable to any directory gets that directory. The static check cannot close this; only a check on the RESOLVED model can (my note 20261101-0200, section 5, second fix). That fix has no card on the queue that I can see. HIGH that it is open.
2. Empty-default and replacement operators build a prefix the checker reads as harmless: `${K:-}<allowed root>/x` and `${K-}<allowed root>/x` pass (K set prepends an arbitrary string); `${K:+<allowed root>}/registry` and `${K+...}` pass (K unset gives `/registry`, a path at the host root). Probe red, 4 cases. The estate files use none of these shapes (grep of the default and GB10 files), so refusing them costs nothing. MEDIUM-LOW.
3. Symlinks and bind-mount order are invisible statically (unchanged; resolved-config plus `realpath` at deploy).
4. Case-insensitive hosts: `./.GIT` and `./.ENV` pass (LOW; Linux is case-sensitive; developers on other systems could bind a repo `.git`).
5. The allowlist root is a single user's home subdirectory spelled in the test file; a different estate user means an edit to the test (a reviewed one-line change: intended).
Steelman: the remaining misses need an operator-controlled variable or a non-Linux host; the allowlist plus the denylist net is far tighter than before.

## 4. Per spelling class (the card's request)
- absolute, `//`, `/./`, `..`, root itself, a prefix that merely starts with the allowed root name (`<root>-evil`, `<root>x`): GREEN.
- `~`, URLs, `service:`/`container:`, backtick, newline, NUL, empty, spaces: GREEN.
- relative escapes (`../../..`, `./a/../../../..`), `.git`, `.env*`, nested `.env`: GREEN; `./a/../../../x` is INSIDE the repository for a compose file two levels down (my expectation was wrong; the checker is right).
- `${V}`, `${V:?}`, nested defaults, `:=`, `=`: GREEN.
- `${V:+r}`, `${V+r}` with an allowed replacement, `${V:-}`/`${V-}` empty default before the root: RED (objection 2).
- new keys: env_file (short and long), secrets.file, configs.file, build.context, additional_contexts, `type: image` source, driver_opts device: GREEN.
- not read: `include`, `extends` (accepted; none on main), `develop.watch.path`, `volumes_from` (donor volumes ARE checked), `sysctls`, `cgroup_parent`, `device_cgroup_rules`, `gpus`/`runtime`.
- namespace sharing: `pid: container:x`, `pid: service:x`, `network_mode: container:x`/`service:x` accepted (`ipc: container:` and `userns_mode: host` refused). The same class as bind sources (a service reaching another's namespace); the estate uses `network_mode: none` only (grep). MEDIUM-LOW.

## 5. Recommendation (each one line, one test)
1. Refuse `${..:+..}`, `${..+..}` and an empty default (`${..:-}`, `${..-}`) anywhere in a source: pin with the four red cases.
2. Allow `pid`, `ipc` and `network_mode` only from an explicit set (`none`, absent); refuse `container:`, `service:`, `host`.
3. Lowercase before the `.git`/`.env` test.
4. The resolved-model check (objection 1) as a card: needs the compose binary in CI, never on the estate host.
5. Make `include` and `extends` a failure while the estate uses neither.

## What I did NOT do
Did not run compose or docker (the rule). Did not check symlinks. Did not read the PR's 285 lines of tests beyond the allowlist function and root list. Did not review the compose files themselves for the owner's real overrides. Did not edit the PR or merge. The "whole tools suite" was not run (missing workspace install here); the compose-pin file passed alone.
