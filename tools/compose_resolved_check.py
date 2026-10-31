#!/usr/bin/env python3
"""Operator check (C-512): apply the C-453 bind-source allowlist to the RESOLVED compose model.

NOT WIRED into any gate or script in this repository (C-715, reviewer C-648 F-C648-4): it is a tool the operator runs
before an `up`, on the host whose files and environment the model names. Calling it "a deploy gate" is the intent,
not a fact, until a script runs it. The deploy runbook (docs/runbooks/v1.2-deploy-rollback.md, before the step that brings
the estate up) names it as an OPTIONAL operator check and says that nothing runs it (C-932, reviewer C-43 F-C387-3).

The static pins in tools/tests/test_compose_static_pins.py validate the DEFAULT of every
`${VAR:-default}` host path. They cannot know what the estate's environment sets, so an operator-controlled
variable (`FIELD_CALLER_KEYS_DIR`, `FIELD_OPERATORS_DIR`, the per-service key directories,
`CLAUDE_APPROVER_SECRETS_DIR`) can still point a bind mount at any directory. `docker compose config` prints the
model after every variable, default and relative path has been resolved; this tool reads that text as DATA and
applies the same rule to the host paths in it:

* a bind source (service volumes of type bind, a named volume's `driver_opts.device`, a top-level secret or config
  `file`, `env_file` paths, `build.context`, `build.additional_contexts`) must be an absolute path that is
  a DESCENDANT of an allowed root: the allowed absolute roots below, or the repository checkout (`--repo-root`);
  never the repository root itself (a build context may be), a `.git` directory or an `.env*` file inside it;
* and it must not be on the denylist (the system trees, container-runtime sockets, a home directory or its
  credential directories).

Read-only: it never starts anything. It runs `docker compose ... config` only when `--run-compose` is given, on the
operator's machine; otherwise it reads a file or stdin. Symlinks are followed only with `--realpath` (it must run on
the host whose files the model names); without it a symlinked source is judged by its spelling.

Not covered: bind-mount ORDER and overlays, a bind source whose parent is replaced after the check, anything the
compose model does not state (a service started by another project), file contents.

Keys this tool does NOT read (C-638, reviewer C-585 F-C585-2; C-715 narrowed the list: `build.dockerfile`,
`devices`, `volumes_from`, `privileged`, the namespace options and any `additional_contexts` scheme other than
`docker-image://` ARE judged now): `build.ssh`, `build.cache_to`, `build.cache_from`, `develop.watch[].path`, a secret's
`environment`, and the `driver_opts` of a named volume other than `device`. None is used by the shipped compose
files. The static pins in tools/tests/test_compose_static_pins.py refuse every one of those keys outright
(the key allowlist, C-500), so the two layers together cover them for the files in the repository; this tool alone does not.
Services whose profiles are not active are omitted by `docker compose config`: `--run-compose` passes `--profile "*"`
so they are judged; a model read from a file or stdin is whatever the operator produced. The host-path rules are shared with the static test: both import them
from tools/compose_bind_rules.py.

usage:
  docker compose -f A -f B config --format json | python tools/compose_resolved_check.py --repo-root <checkout> -
  python tools/compose_resolved_check.py --repo-root <checkout> --run-compose A B
exit: 0 clean, 2 a source is refused, 3 the tool could not do its job: a usage error, a model that could not be read
(a missing file, text that is not UTF-8 or not YAML/JSON, docker failing or timing out), or a model whose shape it does
not know (not a mapping with `services`, a `volumes` that is not a list, a bind source that is not a string ...): no
traceback, never 1; argparse's own exit code 2 would read as "refused", so usage errors are 3 too.

Posture limit, stated (C-823, reviewer C-735 objection 5): of the hardening keys this tool judges `privileged`, `devices`,
`volumes_from` and the namespace options (network_mode, pid, ipc, uts, userns_mode, cgroup). It does NOT read `cap_add`,
`cap_drop`, `security_opt` or `ports` (allowed keys, used in the shipped files) nor `user`, `sysctls` or `ulimits`
(unknown keys, refused by the static pins): no compose variable in the shipped files feeds any of them, and if one ever
did nothing in the resolved model would be checked. Under --realpath the allowed roots are resolved too, and a
source is resolved from the string as written (a `..` after a link is followed physically); a duplicated key in a JSON
model is read last-wins (`docker compose config` never emits one).

Out of scope, stated (C-723, reviewer C-698): the `--repo-root` value is trusted as given (it is the operator's
argument: `--repo-root /tmp` allows every source under /tmp; `/` refuses everything); `--help` exits 0 as argparse
does, it checks nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, Iterable

try:
    import yaml
except ImportError:  # C-1015 (reviewer C-939 F-C939-1): a host without PyYAML still reads the JSON `config --format json` prints
    yaml = None

# C-723 (cloud/reviewer C-698 objection 4): the tools directory goes on the path explicitly, so the sibling import
# works under `python -I`, `-P` and PYTHONSAFEPATH=1 (a hardened wrapper), not only when the script directory is implied
# C-823 (C-735 objection 6): realpath, not abspath, so a symlink to this script in another directory still finds its sibling
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

try:
    from compose_bind_rules import (  # noqa: E402  the rules the static pins use: one definition (C-512)
        A_HOME, ALLOWED_ABSOLUTE_ROOTS, FORBIDDEN_BIND_EXACT, FORBIDDEN_BIND_TREES, FORBIDDEN_HOME_DIRS,
        FORBIDDEN_HOME_PARENTS, NAMESPACE_OPTIONS, RUNTIME_SOCKET, name_problem, namespace_problem)
except ImportError as exc:  # C-932 (reviewer C-43 F-C387-1): the script copied ALONE is a usage error (exit 3), not a traceback
    print(f"compose-resolved: could not import compose_bind_rules ({type(exc).__name__}): keep the script next to "
          "tools/compose_bind_rules.py (copy both files, or run it from the checkout)")
    raise SystemExit(3)


def normal(path: str) -> str:
    """`path` with `//`, `/./` and `/..` resolved ("/.." is the root)."""
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _denied(path: str) -> bool:
    return (path in FORBIDDEN_BIND_EXACT or bool(A_HOME.search(path)) or bool(FORBIDDEN_HOME_DIRS.search(path))
            or bool(FORBIDDEN_HOME_PARENTS.search(path)) or bool(RUNTIME_SOCKET.search(path))
            or any(path == tree or path.startswith(tree + "/") for tree in FORBIDDEN_BIND_TREES))


def source_problem(source: Any, repo_root: str, kind: str = "volume",
                   realpath: Callable[[str], str] | None = None) -> str | None:
    """None when `source` may be bound, else the reason. `kind`: "volume", "file" or "build-context" (the repository
    root itself is allowed there)."""
    if not isinstance(source, str):
        return None                                  # a sourceless volume (tmpfs, anonymous) has no host path
    if not source.strip():
        return "empty"
    if "$" in source or "`" in source or "\n" in source or "\0" in source:
        return "not a resolved literal path"
    if not source.startswith("/"):
        return "not absolute (the model is not resolved)"
    path = normal(source)
    if _denied(path):
        return "on the denylist"
    roots = list(ALLOWED_ABSOLUTE_ROOTS)
    if realpath is not None:
        # C-823 (C-735 F-C735-3): the ORIGINAL string is resolved, so a `..` after a link is followed physically, as the
        # kernel does (`<repo>/link_out/../x` is not `<repo>/x`), after the lexical form was judged above
        path = normal(realpath(source))
        if _denied(path):
            return "on the denylist"
        # C-823 (C-735 F-C735-1): the allowed roots are resolved the same way, so a root that is itself a symlink (or sits
        # behind one) does not refuse the legitimate bind under --realpath; the declared spelling stays allowed too
        roots += [normal(realpath(root)) for root in ALLOWED_ABSOLUTE_ROOTS]
    root = normal(repo_root)
    if path == root:
        return None if kind == "build-context" else "the repository root itself"
    if path.startswith(root + "/"):
        return name_problem(path[len(root) + 1:].split("/"))      # C-715: the shared, case-insensitive name rule
    if any(path.startswith(allowed + "/") for allowed in roots):
        return None
    return "outside the repository and the allowed roots"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):                     # argparse exits 2, which this tool uses for "a source is refused"
        self.print_usage(sys.stderr)
        print(f"compose-resolved: usage error: {message}")
        raise SystemExit(3)


def _env_file_paths(value: Any) -> Iterable[Any]:
    """Every `env_file` path as written; a non-string one is yielded too, so it is reported, never skipped (C-823)."""
    if value is not None and not isinstance(value, (str, dict, list)):
        raise ValueError("env_file is neither a string, a mapping nor a list")
    for item in ([value] if isinstance(value, (str, dict)) else list(value or [])):
        yield item.get("path") if isinstance(item, dict) else item


def check_model(model: Any, repo_root: str, realpath: Callable[[str], str] | None = None) -> list[str]:
    """Problems in a resolved compose model (the parsed text of `docker compose config`)."""
    out: list[str] = []
    if not isinstance(model, dict) or not isinstance(model.get("services"), dict):
        # C-723 (C-698 objection 3): not a compose model is "a shape this tool does not know" (exit 3), not a refusal
        raise ValueError("the model has no services: it is not the output of `docker compose config`")
    if not model["services"]:
        # C-715 (C-648 F-C648-7): a wrong -f file or an empty project is not a clean pass
        raise ValueError("the model has an empty service map: nothing to check (a wrong -f file?)")

    def judge(where: str, source: Any, kind: str = "volume", must_be_text: bool = False) -> None:
        if must_be_text and not isinstance(source, str):
            out.append(f"{where}: {source!r} is not a string")      # C-723 (C-698 objection 2): never read as clean
            return
        why = source_problem(source, repo_root, kind, realpath)
        if why:
            out.append(f"{where}: {source!r} {why}")

    for vname, vol in sorted((model.get("volumes") or {}).items()):
        opts = vol.get("driver_opts") if isinstance(vol, dict) else None
        if isinstance(opts, dict) and opts.get("device") is not None:
            if opts.get("type") == "tmpfs" or opts.get("device") == "tmpfs":
                continue                        # C-715 (C-648 F-C648-8): `device: tmpfs` names a kernel file system, not a path
            judge(f"volume {vname}: driver_opts.device", opts.get("device"), must_be_text=True)
    for section in ("secrets", "configs"):
        for name, definition in sorted((model.get(section) or {}).items()):
            if isinstance(definition, dict) and definition.get("file") is not None:
                judge(f"{section[:-1]} {name}: file", definition.get("file"), "file", must_be_text=True)
    for name, svc in sorted(model["services"].items()):
        if not isinstance(svc, dict):
            # C-823 (C-735 F-C735-2): a string, a list or null is not an empty service, it is not a compose model
            raise ValueError(f"service {name}: the service is not a mapping")
        volumes = svc.get("volumes") or []
        if not isinstance(volumes, list):
            raise ValueError(f"service {name}: volumes is not a list")
        for vol in volumes:
            if isinstance(vol, dict):
                if vol.get("type") in (None, "bind") and "source" in vol:
                    judge(f"service {name}: volume", vol.get("source"), must_be_text=True)
            elif isinstance(vol, str) and ":" in vol and not vol.startswith(("tmpfs", "volume")):
                head = vol.split(":")[0]
                if head.startswith(("/", ".", "~", "$")):
                    judge(f"service {name}: volume", head)
        # C-715 (C-640 F-C640-6): the resolved model has literal values, so the host-level options are judged here too,
        # with the SAME sets as the static pins (an interpolated `${VAR}` namespace is no longer invisible)
        for option in NAMESPACE_OPTIONS:
            value = svc.get(option)
            if value is not None and not isinstance(value, str):
                out.append(f"service {name}: {option}: {value!r} is not a string")
            elif namespace_problem(option, value):
                out.append(f"service {name}: {namespace_problem(option, value)}")
        if svc.get("privileged"):
            out.append(f"service {name}: privileged")
        if svc.get("devices"):
            out.append(f"service {name}: devices {svc.get('devices')!r}")
        if svc.get("volumes_from"):
            out.append(f"service {name}: volumes_from {svc.get('volumes_from')!r}")
        for path in _env_file_paths(svc.get("env_file")):
            judge(f"service {name}: env_file", path, "file", must_be_text=True)
        build = svc.get("build")
        build = {"context": build} if isinstance(build, str) else build
        if build is not None and not isinstance(build, dict):
            raise ValueError(f"service {name}: build is neither a string nor a mapping")
        if isinstance(build, dict):
            if "context" in build:
                judge(f"service {name}: build.context", build.get("context"), "build-context", must_be_text=True)
            dockerfile = build.get("dockerfile")
            if isinstance(dockerfile, str) and dockerfile:
                # C-715 (C-648 F-C648-2): a resolved model prints `dockerfile` relative to the context
                context = build.get("context")
                whole = dockerfile if dockerfile.startswith("/") or not isinstance(context, str) else normal(context + "/" + dockerfile)
                judge(f"service {name}: build.dockerfile", whole, "file")
            elif dockerfile is not None and not isinstance(dockerfile, str):
                out.append(f"service {name}: build.dockerfile {dockerfile!r} is not a string")
            if build.get("dockerfile_inline") is not None:
                out.append(f"service {name}: build.dockerfile_inline is not allowed")
            extra = build.get("additional_contexts") or {}
            values = [v.partition("=")[2] for v in extra] if isinstance(extra, list) else list(extra.values())
            for value in values:
                if not isinstance(value, str):
                    out.append(f"service {name}: build.additional_contexts value {value!r} is not a string")
                elif value.startswith("docker-image://"):
                    continue                    # an image reference, not a host path
                elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
                    # C-715 (C-648 F-C648-1): ANY other scheme is refused (`file:///`, `oci-layout:///` read local
                    # directories, `https://`/`git://` fetch remote code); it used to be skipped as "not a host path"
                    out.append(f"service {name}: build.additional_contexts: {value!r} a scheme other than docker-image://")
                else:
                    judge(f"service {name}: build.additional_contexts", value, "file")
    return out


class NoYamlError(ValueError):
    """The text is not JSON and PyYAML is missing (C-1015). Its message is fixed text, safe to print: other read errors
    print only their type, because their messages can quote the model."""


def load_model(text: str) -> Any:
    try:
        return json.loads(text)                # what `docker compose config --format json` prints: no PyYAML needed
    except ValueError:
        if yaml is None:
            raise NoYamlError("the text is not JSON and PyYAML is not installed (pip install pyyaml, or pass the output of "
                              "`docker compose config --format json`)") from None
        return yaml.safe_load(text)            # YAML text (a hand-written model) is read as before


def run_compose_config(files: list[str], project_dir: str | None = None) -> str:
    """The resolved model, from `docker compose -f ... config --format json`. Read-only (`config` starts nothing)."""
    cmd = ["docker", "compose"]
    for f in files:
        cmd += ["-f", f]
    if project_dir:
        cmd += ["--project-directory", project_dir]
    # --profile "*" (C-715, C-648 F-C648-3): `config` omits services whose profiles are not active; the tree has profiled
    # services (the approver, the GB10 admin jobs), and their binds must be judged too
    cmd += ["--profile", "*", "config", "--format", "json"]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"docker compose config exited {done.returncode}")
    return done.stdout


def main(argv: list[str] | None = None) -> int:
    p = _Parser(description="apply the compose bind-source allowlist to a resolved compose model")
    p.add_argument("model", nargs="?", help="a file holding the output of `docker compose config`, or - for stdin")
    p.add_argument("--repo-root", required=True, help="the repository checkout the compose project belongs to")
    p.add_argument("--realpath", action="store_true",
                   help="follow symlinks (run it on the host whose files the model names)")
    p.add_argument("--run-compose", nargs="+", metavar="FILE",
                   help="run `docker compose -f FILE ... config --format json` here (read-only; the operator's machine "
                        "only), e.g. --run-compose docker-compose.yml docker-compose.gb10.yml")
    args = p.parse_args(argv)
    try:
        if args.run_compose:
            text = run_compose_config(args.run_compose)
        elif args.model:
            text = sys.stdin.read() if args.model == "-" else open(args.model, encoding="utf-8").read()
        else:
            p.error("give a model file, - for stdin, or --run-compose")
        model = load_model(text)
    except (OSError, RuntimeError, ValueError, *((yaml.YAMLError,) if yaml else ()), subprocess.SubprocessError) as exc:
        # ValueError covers UnicodeDecodeError (C-723, C-698 objection 1: text that is not UTF-8 exited 1 with a traceback)
        print(f"compose-resolved: could not read the model ({type(exc).__name__})"
              + (f": {exc}" if isinstance(exc, NoYamlError) else ""))
        return 3
    # C-638 F-C585-1: with --realpath the repository root is resolved too (a checkout reached through a symlink would
    # otherwise be refused on every source), and a model shape the tool does not know is exit 3, never a traceback
    repo_root = os.path.realpath(args.repo_root) if args.realpath else args.repo_root
    try:
        problems = check_model(model, repo_root, os.path.realpath if args.realpath else None)
    except Exception as exc:  # noqa: BLE001 - any unexpected shape is "could not check", never a crash
        print(f"compose-resolved: the model has a shape this tool does not know ({type(exc).__name__}): not checked")
        return 3
    for line in problems:
        print(f"compose-resolved: REFUSED {line}")
    if not problems:
        print("compose-resolved: every bind source is allowed")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
