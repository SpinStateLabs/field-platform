#!/usr/bin/env python3
"""Deploy-gate check (C-512): apply the C-453 bind-source allowlist to the RESOLVED compose model.

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
compose model does not state (a service started by another project), file contents, and the options that are not host
paths (network, devices, capabilities: those stay with the static pins). The host-path rules are shared with the
static test: both import them from tools/compose_bind_rules.py.

usage:
  docker compose -f A -f B config --format json | python tools/compose_resolved_check.py --repo-root <checkout> -
  python tools/compose_resolved_check.py --repo-root <checkout> --run-compose A B
exit: 0 clean, 2 a source is refused, 3 the model could not be read.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Any, Callable, Iterable

import yaml

from compose_bind_rules import (  # the rules the static pins use: one definition (C-512)
    A_HOME, ALLOWED_ABSOLUTE_ROOTS, FORBIDDEN_BIND_EXACT, FORBIDDEN_BIND_TREES, FORBIDDEN_HOME_DIRS,
    FORBIDDEN_HOME_PARENTS, RUNTIME_SOCKET)


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
    if realpath is not None:
        path = normal(realpath(path))
    if _denied(path):
        return "on the denylist"
    root = normal(repo_root)
    if path == root:
        return None if kind == "build-context" else "the repository root itself"
    if path.startswith(root + "/"):
        names = path[len(root) + 1:].split("/")
        if ".git" in names:
            return "inside .git"
        if names[-1] == ".env" or names[-1].startswith(".env."):
            return "an .env file"
        return None
    if any(path.startswith(allowed + "/") for allowed in ALLOWED_ABSOLUTE_ROOTS):
        return None
    return "outside the repository and the allowed roots"


def _iter_env_files(value: Any) -> Iterable[str]:
    for item in ([value] if isinstance(value, (str, dict)) else list(value or [])):
        path = item.get("path") if isinstance(item, dict) else item
        if isinstance(path, str):
            yield path


def check_model(model: Any, repo_root: str, realpath: Callable[[str], str] | None = None) -> list[str]:
    """Problems in a resolved compose model (the parsed text of `docker compose config`)."""
    out: list[str] = []
    if not isinstance(model, dict) or not isinstance(model.get("services"), dict):
        return ["the model has no services: it is not the output of `docker compose config`"]

    def judge(where: str, source: Any, kind: str = "volume") -> None:
        why = source_problem(source, repo_root, kind, realpath)
        if why:
            out.append(f"{where}: {source!r} {why}")

    for vname, vol in sorted((model.get("volumes") or {}).items()):
        opts = vol.get("driver_opts") if isinstance(vol, dict) else None
        if isinstance(opts, dict) and opts.get("device") is not None:
            judge(f"volume {vname}: driver_opts.device", opts.get("device"))
    for section in ("secrets", "configs"):
        for name, definition in sorted((model.get(section) or {}).items()):
            if isinstance(definition, dict) and definition.get("file") is not None:
                judge(f"{section[:-1]} {name}: file", definition.get("file"), "file")
    for name, svc in sorted(model["services"].items()):
        svc = svc if isinstance(svc, dict) else {}
        for vol in svc.get("volumes") or []:
            if isinstance(vol, dict):
                if vol.get("type") in (None, "bind") and "source" in vol:
                    judge(f"service {name}: volume", vol.get("source"))
            elif isinstance(vol, str) and ":" in vol and not vol.startswith(("tmpfs", "volume")):
                head = vol.split(":")[0]
                if head.startswith(("/", ".", "~", "$")):
                    judge(f"service {name}: volume", head)
        for path in _iter_env_files(svc.get("env_file")):
            judge(f"service {name}: env_file", path, "file")
        build = svc.get("build")
        build = {"context": build} if isinstance(build, str) else build
        if isinstance(build, dict):
            judge(f"service {name}: build.context", build.get("context"), "build-context")
            extra = build.get("additional_contexts") or {}
            values = [v.partition("=")[2] for v in extra] if isinstance(extra, list) else list(extra.values())
            for value in values:
                if isinstance(value, str) and not value.startswith("docker-image://") and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
                    judge(f"service {name}: build.additional_contexts", value, "file")
    return out


def load_model(text: str) -> Any:
    return yaml.safe_load(text)           # `docker compose config --format json` is valid YAML


def run_compose_config(files: list[str], project_dir: str | None = None) -> str:
    """The resolved model, from `docker compose -f ... config --format json`. Read-only (`config` starts nothing)."""
    cmd = ["docker", "compose"]
    for f in files:
        cmd += ["-f", f]
    if project_dir:
        cmd += ["--project-directory", project_dir]
    cmd += ["config", "--format", "json"]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"docker compose config exited {done.returncode}")
    return done.stdout


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="apply the compose bind-source allowlist to a resolved compose model")
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
    except (OSError, RuntimeError, yaml.YAMLError, subprocess.SubprocessError) as exc:
        print(f"compose-resolved: could not read the model ({type(exc).__name__})")
        return 3
    problems = check_model(model, args.repo_root, os.path.realpath if args.realpath else None)
    for line in problems:
        print(f"compose-resolved: REFUSED {line}")
    if not problems:
        print("compose-resolved: every bind source is allowed")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
