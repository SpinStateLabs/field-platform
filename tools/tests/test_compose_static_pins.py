"""C-323 (reviewer C-263 F-C263-5, C-264 F-C264-1/-5): nothing pinned the image pins or the hardening.

Static, no docker: the Dockerfiles and the two compose files are read as text and parsed, and
  * every `FROM` is digest-pinned and every `pip install` in a Dockerfile is constrained
    (`-c integration/constraints.txt`, which names the approver's own dependencies too);
  * every `COPY --from=<image>` that names an image rather than a build stage is digest-pinned (C-332);
  * every compose `image:` is digest-pinned;
  * every healthcheck probes the port its service's own `--port` starts on;
  * every service of the merged base + GB10 compose carries no-new-privileges and `cap_drop: [ALL]`,
    and a read-only root unless it is named in READ_ONLY_EXEMPT with its reason (a new service added
    without the block fails here; the approver and the five GB10-only services did, until C-323);
  * a hardened service is not re-escalated (C-332, reviewer C-331 F-C331-4): `cap_add` stays inside an
    explicit per-service allow-list, no `privileged`, no docker socket mount, and a read-only root keeps
    its tmpfs;
  * every constraint is an exact `name==version`, and the approver closure's versions are pinned (F-C331-5).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "integration" / "demo"
DOCKERFILES = ["integration/demo/Dockerfile", "integration/fly/Dockerfile", "services/claude-approver/Dockerfile"]

# service -> why its root file system is not read-only (everything else must be)
# service -> the only capabilities it may add back after `cap_drop: [ALL]`; a service not listed gets
# DAC_READ_SEARCH (read the host-owned 0600 files its bind mounts hold), the base file's stage-1 block
CAP_ADD_ALLOWED = {
    "proxy": {"NET_BIND_SERVICE"},
    "keys-admin": set(),
    "attest-keys-admin": set(),
    "canary-agent": set(),
}
CAP_ADD_DEFAULT = {"DAC_READ_SEARCH"}

READ_ONLY_EXEMPT = {
    "proxy": "caddy keeps its state under /data and /config; hardened by C-151 without read_only",
}
# service -> why it has no healthcheck although it serves on a --port
HEALTHCHECK_EXEMPT = {
    "canary-agent": "GB10-only canary on the internal network, no /health route (GET /status exists); "
                    "a healthcheck was not added blind in C-323",
}


class _Loader(yaml.SafeLoader):
    pass


class _Override:
    """`key: !override value`: the later file replaces the earlier value instead of merging with it."""

    def __init__(self, value):
        self.value = value


class _Reset:
    """`key: !reset null` (or `[]`): the later file REMOVES the key the earlier file set (compose v2.24+)."""

    def __init__(self, value):
        self.value = value


def _tagged(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    if suffix == "override":
        return _Override(value)
    if suffix == "reset":
        return _Reset(value)
    return value


_Loader.add_multi_constructor("!", _tagged)


def _unwrap(value):
    if isinstance(value, _Override):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items() if not isinstance(v, _Reset)}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


# service-relative key paths that compose REPLACES instead of appending when both files give a list
REPLACED_PATHS = {("command",), ("entrypoint",), ("healthcheck", "test")}


def _merge(base, over, path=()):
    """Compose's file merge: maps merge key by key, lists APPEND (cap_add, security_opt, volumes, ...) except
    `command`, `entrypoint` and `healthcheck.test`, which are replaced; a scalar is replaced; `!override`
    replaces whatever the earlier file had; `!reset` removes the key (C-348, reviewer C-347 F-C347-1)."""
    if isinstance(over, _Override):
        return _unwrap(over)
    if isinstance(base, dict) and isinstance(over, dict):
        merged = dict(base)
        for key, value in over.items():
            if isinstance(value, _Reset):
                merged.pop(key, None)
            elif key in base:
                merged[key] = _merge(base[key], value, path + (key,))
            else:
                merged[key] = _unwrap(value)
        return merged
    if isinstance(base, list) and isinstance(over, list) and path not in REPLACED_PATHS:
        return base + _unwrap(over)
    return _unwrap(over)


def _services(base_text: str, gb10_text: str) -> dict[str, dict]:
    """service -> its keys after the base file then the GB10 file, merged the way compose merges them (C-344,
    reviewer C-343 F-C343-3): a GB10 `cap_add` is ADDED to the base list, not a replacement of it."""
    merged: dict[str, dict] = {}
    for text in (base_text, gb10_text):
        for name, svc in (yaml.load(text, _Loader).get("services") or {}).items():
            if isinstance(svc, _Reset):          # `registry: !reset null`: compose drops the whole service (F-C360-3)
                merged.pop(name, None)
                continue
            merged[name] = _merge(merged[name], svc) if name in merged else _unwrap(svc)
    return merged


def _logical_lines(text: str) -> list[str]:
    return re.sub(r"\\\r?\n", " ", text).splitlines()


def check_dockerfile(name: str, text: str) -> None:
    stages = {m.group(1).lower() for m in re.finditer(r"^\s*FROM\s+\S+\s+AS\s+(\S+)", text, re.I | re.M)}
    for line in _logical_lines(text):
        s = line.strip()
        copy = re.match(r"COPY\s+(?:--\S+\s+)*--from=(\S+)", s, re.I)
        if copy and copy.group(1).lower() not in stages and not copy.group(1).isdigit():
            assert "@sha256:" in copy.group(1), f"{name}: COPY --from an image without a digest: {s}"
        if s.upper().startswith("FROM "):
            assert "@sha256:" in s, f"{name}: FROM without a digest: {s}"
        if s.upper().startswith("RUN ") and "pip install" in s:
            assert re.search(r"\s-c\s+integration/constraints\.txt\b", s), f"{name}: pip install without -c: {s}"


# Host paths no service may bind (C-361, reviewer C-360 F-C360-2): the root, and the trees that hand over the
# host's configuration, kernel interfaces or container runtime. Compared after normalisation (below).
# C-391 (reviewer C-371 F-C371-2/-3): the comment says trees, so these are trees. FORBIDDEN_BIND_TREES: the path
# and everything under it (/etc/shadow, /etc/ssh, /proc/1/root, /var/lib/docker/volumes, /dev/mem ...).
# FORBIDDEN_BIND_EXACT: the path itself only (the whole of /home, /var, /usr, or the root), because a service may
# legitimately bind a directory BELOW them (the GB10 caller-key directories live under /home).
# C-402 (reviewer C-399 F-C399-1): /run (and with it /var/run's target and the runtime sockets of containerd, podman and
# CRI-O), the container runtimes' state under /var/lib, the parent /var/lib itself, and the credential directories
# below /home (a bind of /home/<user>/.ssh is as bad as /root/.ssh; binds of other directories below /home stay legal).
# C-426 (reviewer C-424 F-C424-1): the parent of a forbidden path is the same bypass as /var/lib was, so a home directory
# itself is exact-forbidden, the credential directories of a home are listed in full, ${HOME} reads as a home, the
# repository root and its .git and .env by a relative path are refused, and more runtime state under /var/lib.
FORBIDDEN_BIND_TREES = ("/etc", "/proc", "/sys", "/var/lib/docker", "/var/lib/containerd", "/var/lib/kubelet", "/var/run",
                        "/var/lib/lxd", "/var/lib/lxc", "/var/lib/rancher", "/var/lib/k0s", "/var/lib/etcd", "/var/lib/snapd",
                        "/var/lib/containers", "/var/lib/podman", "/var/lib/libvirt", "/var/lib/k3s", "/var/lib/microk8s",
                        "/var/lib/kubernetes", "/var/lib/cni", "/var/lib/buildkit", "/var/lib/nerdctl", "/var/lib/crio",
                        "/run", "/root", "/dev", "/boot")
FORBIDDEN_BIND_EXACT = {"/", "/home", "/var", "/var/lib", "/usr", "/lib", "/bin", "/sbin", "/opt", "/srv", "/mnt", "/media"}
FORBIDDEN_HOME_DIRS = re.compile(
    r"^/home/[^/]+/\.(ssh|aws|docker|gnupg|kube|azure|netrc|npmrc|git-credentials|config/gcloud|local/share/keyrings"
    r"|config/gh|config/rclone|pgpass|my\.cnf|vault-token|s3cfg|boto|oci|terraform\.d|pypirc|cargo|m2|gradle|password-store"
    r"|bash_history|mozilla|pki"
    # C-442 (reviewers C-441, Lane 5 F-C441-1/-5 and Lane 4 F-C441-2): more credential places, and the history files
    r"|config/git|config/helm|config/doctl|config/op|config/1Password|config/containers|config/sops|config/age|age"
    r"|terraformrc|gitconfig|gcloud|helm|minikube|ansible|dockercfg|credentials|secrets|ssh2|pg_service\.conf|mongorc\.js"
    r"|1password|python_history|zsh_history|history|rediscli_history|psql_history|mysql_history)(/|$)")
# C-442 (Lane 5 F-C441-1): the PARENT of a credential tree is the same bypass as /var/lib was: a bind of ~/.config hands
# over config/gh, config/rclone and config/gcloud at once, ~/.local/share the keyrings. Exact paths: a directory
# below them that is not listed (~/.config/myapp, ~/.local/bin) stays legal.
FORBIDDEN_HOME_PARENTS = re.compile(r"^/home/[^/]+/\.(config|local|local/share)$")
A_HOME = re.compile(r"^/home/[^/]+$")
RUNTIME_SOCKET = re.compile(
    r"(^|/)(docker|dockerd|containerd|containerd-shim|podman|crio|cri-o|cri-dockerd|dockershim|buildkitd|nerdctl|rootlesskit"
    r"|k3s|kubelet|libpod|docker-rootless|isulad|cri-docker|agent|ssh-agent|gpg-agent)\.sock$"
    r"|(^|/)S\.gpg-agent(\.[a-z]+)?$|(^|/)(snapd|lxd)\.socket$")
# C-435 (reviewer C-434 F-C434-1/-2): variables whose meaning is settled wherever compose runs. HOME is always set, so
# `${HOME:-/tmp}/.ssh` is the home directory's .ssh, not /tmp/.ssh: they are read as their value BEFORE any default
# is expanded, whatever the operator (`:-`, `-`, `:=`, `:+`, `:?`, none).
SETTLED_VARIABLES = {
    "HOME": "/home/_user",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "SSH_AUTH_SOCK": "/run/user/1000/ssh-agent.sock",
    "XDG_CONFIG_HOME": "/home/_user/.config",
    "DOCKER_HOST": "/var/run/docker.sock",
    # C-442 (Lane 4 F-C441-1, Lane 5 F-C441-2), decision: PWD is the directory compose runs in, the repository root in
    # the runbook and `integration/demo` in CI. It is read as the REPOSITORY ROOT (the stricter reading, relative to
    # the compose files): `${PWD}` and `${PWD}/..` are refused like `../..` and `../../..`, `${PWD}/.git` like
    # `../../.git`, while `${PWD}/manifests` stays a directory of the repository.
    "PWD": "../..",
    "OLDPWD": "../..",
}
# C-442 (Lane 4 F-C441-2, Lane 5 F-C441-2), decision: a variable that names a credential location WHEN SET is refused as
# a bind source (alone, with a default, or as the head of a path), because its value is the credential place. A
# variable with no known meaning stays allowed (the estate's .env decides) unless its path continues with a credential
# name (`${DATA_DIR}/.ssh`).
CREDENTIAL_VARIABLES = (
    "GNUPGHOME", "KUBECONFIG", "DOCKER_CONFIG", "AWS_SHARED_CREDENTIALS_FILE", "GOOGLE_APPLICATION_CREDENTIALS",
    "KRB5CCNAME", "HISTFILE", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "CONTAINER_HOST",
)
CREDENTIAL_VARIABLE_HEAD = re.compile(r"^\$\{?(" + "|".join(CREDENTIAL_VARIABLES) + r")(?![A-Za-z0-9_])")
UNRESOLVED_HEAD = re.compile(r"^\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)(/.*)$")
FORBIDDEN_BIND_SOURCES = FORBIDDEN_BIND_EXACT | set(FORBIDDEN_BIND_TREES)   # kept for the normalisation tests


def _expand_defaults(source: str) -> str:
    """`${VAR:-d}`, `${VAR-d}`, `${VAR:=d}`, `${VAR=d}` read as their default (what an unset estate .env gives) and
    `${VAR:+r}`, `${VAR+r}` as their replacement (what a set one gives), innermost first so a nested
    `${A:-${B:-/}}` is the root too. `${VAR}` and `$VAR` with no default are unknown and left as they are: a
    static check cannot tell what the estate's .env sets (the pins say so)."""
    source = _read_settled_variables(source)
    pattern = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=+]([^${}]*)\}")
    for _ in range(16):
        expanded = pattern.sub(r"\1", source)
        if expanded == source:
            break
        source = expanded
    return source


def _read_settled_variables(source: str) -> str:
    """Replace `${NAME}`, `${NAME<operator>...}` (balanced braces, a nested default included) and a bare `$NAME` of a
    SETTLED_VARIABLES name by its value, before anything else is expanded (C-435)."""
    out, i = [], 0
    while i < len(source):
        m = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)").match(source, i)
        if m and m.group(1) in SETTLED_VARIABLES and m.end() < len(source) and source[m.end()] in ":-=+?}":
            depth, j = 1, m.end()
            while j < len(source) and depth:
                depth += (source[j] == "{") - (source[j] == "}")
                j += 1
            if depth == 0:
                out.append(SETTLED_VARIABLES[m.group(1)])
                i = j
                continue
        bare = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)").match(source, i)
        if bare and bare.group(1) in SETTLED_VARIABLES:
            out.append(SETTLED_VARIABLES[bare.group(1)])
            i = bare.end()
            continue
        out.append(source[i])
        i += 1
    return "".join(out)


COMPOSE_DIR_DEPTH = 2          # the compose files live in integration/demo: `../..` is the repository root


def _relative_source_escapes(source: str) -> bool:
    """A `~` source (compose expands it to the user's home) or a relative one that climbs out of the REPOSITORY
    (more than COMPOSE_DIR_DEPTH levels above the compose file: `../../../etc`). `../../manifests` is a directory of
    this repository and is fine. A bare name is a named volume."""
    if source.startswith("~"):
        return True
    if not (source == "." or source.startswith("./") or source.startswith("../") or source == ".."):
        return False
    ups, names = 0, []
    for part in source.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if names:
                names.pop()
            else:
                ups += 1
                if ups > COMPOSE_DIR_DEPTH:
                    return True
        else:
            names.append(part)
    # C-426: the repository root itself (`../..`), anything named .git on the way, and an .env file (`./.env`,
    # `../../.env`) hold the whole tree or its secrets
    if ups == COMPOSE_DIR_DEPTH and not names:
        return True
    return ".git" in names or any(n == ".env" or n.startswith(".env.") for n in names[-1:])


def _binds_forbidden_host_path(source) -> bool:
    if not isinstance(source, str):
        return False
    if CREDENTIAL_VARIABLE_HEAD.search(source.strip()):
        return True
    expanded = _expand_defaults(source)
    if _relative_source_escapes(expanded):
        return True
    path = _normal_root(expanded)
    head = UNRESOLVED_HEAD.match(path)
    if head and (FORBIDDEN_HOME_DIRS.search("/home/_user" + head.group(2))
                 or FORBIDDEN_HOME_PARENTS.search("/home/_user" + head.group(2))):
        return True                    # `${DATA_DIR}/.ssh`: the head is unknown, the credential tail is not
    if (path in FORBIDDEN_BIND_EXACT or A_HOME.search(path) or FORBIDDEN_HOME_DIRS.search(path)
            or FORBIDDEN_HOME_PARENTS.search(path) or RUNTIME_SOCKET.search(path)):
        return True
    return any(path == tree or path.startswith(tree + "/") for tree in FORBIDDEN_BIND_TREES)


def _normal_root(source) -> str:
    """The absolute host path `source` names with `//`, `/./` and `/..` resolved ("//", "/./" and "/.." are all
    the root); anything that is not absolute (a named volume, a relative path) is returned unchanged."""
    if not isinstance(source, str) or not source.startswith("/"):
        return str(source)
    parts: list[str] = []
    for part in source.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _short_source(volume: str) -> str:
    """The host side of a `source:target[:mode]` volume string; a `${VAR:-default}` keeps its `:-`."""
    masked = re.sub(r"\$\{[^}]*\}", lambda m: m.group(0).replace(":", "\0"), volume)
    return masked.split(":")[0].replace("\0", ":")


def _top_level_volumes(base_text: str, gb10_text: str) -> dict[str, dict]:
    """Named volume -> its definition after both files (a `!reset null` drops it)."""
    merged: dict[str, dict] = {}
    for text in (base_text, gb10_text):
        for name, vol in (yaml.load(text, _Loader).get("volumes") or {}).items():
            if isinstance(vol, _Reset):
                merged.pop(name, None)
            else:
                if name in merged and vol is None:
                    continue                      # a null override: keep the base definition (the stricter reading)
                merged[name] = _merge(merged[name], vol) if name in merged else (_unwrap(vol) or {})
                merged[name] = merged[name] or {}
    return merged


def check_compose(base_text: str, gb10_text: str) -> None:
    services = _services(base_text, gb10_text)
    # C-402: a named volume that binds a host directory through driver_opts (`type: none, o: bind, device: /`) is a
    # bind like any other, whichever service mounts it
    for vname, vol in sorted(_top_level_volumes(base_text, gb10_text).items()):
        device = (vol.get("driver_opts") or {}).get("device") if isinstance(vol, dict) else None
        assert not _binds_forbidden_host_path(device), f"volume {vname}: binds a host path it must not: {device}"
    for name, svc in sorted(services.items()):
        if "image" in svc:
            assert "@sha256:" in svc["image"], f"{name}: image without a digest: {svc['image']}"
        assert "no-new-privileges:true" in (svc.get("security_opt") or []), f"{name}: no no-new-privileges"
        assert svc.get("cap_drop") == ["ALL"], f"{name}: cap_drop is not [ALL]"
        if name not in READ_ONLY_EXEMPT:
            assert svc.get("read_only") is True, f"{name}: root file system not read-only"
            assert svc.get("tmpfs"), f"{name}: a read-only root without a tmpfs /tmp"
        extra = set(svc.get("cap_add") or []) - CAP_ADD_ALLOWED.get(name, CAP_ADD_DEFAULT)
        assert not extra, f"{name}: capabilities added back beyond the allow-list: {sorted(extra)}"
        assert not svc.get("privileged"), f"{name}: privileged"
        # C-348 (reviewer C-347 F-C347-3): the host-level options that undo the container boundary
        assert svc.get("network_mode") != "host", f"{name}: network_mode host"
        for key in ("pid", "ipc", "uts", "userns_mode", "cgroup"):
            assert svc.get(key) != "host", f"{name}: {key}: host"
        assert not svc.get("devices"), f"{name}: devices {svc.get('devices')}"
        assert not any("unconfined" in str(o) for o in svc.get("security_opt") or []), \
            f"{name}: an unconfined security_opt"
        for vol in svc.get("volumes") or []:
            assert "docker.sock" not in str(vol), f"{name}: mounts the docker socket: {vol}"
            source = vol.get("source") if isinstance(vol, dict) else _short_source(str(vol))
            assert not _binds_forbidden_host_path(source), f"{name}: binds a host path it must not: {vol}"
        command = svc.get("command")
        text = " ".join(command) if isinstance(command, list) else str(command or "")
        port = re.search(r"--port\s+(\d+)", text)
        test = (svc.get("healthcheck") or {}).get("test")
        if port and name not in HEALTHCHECK_EXEMPT:
            assert test, f"{name}: serves on {port.group(1)} but has no healthcheck"
            probed = re.search(r"127\.0\.0\.1:(\d+)/", " ".join(test))
            assert probed and probed.group(1) == port.group(1), f"{name}: healthcheck port is not its --port {port.group(1)}"
    assert set(READ_ONLY_EXEMPT) <= set(services), "READ_ONLY_EXEMPT names a service that no longer exists"


def _texts() -> tuple[dict[str, str], str, str]:
    return ({d: (ROOT / d).read_text(encoding="utf-8") for d in DOCKERFILES},
            (DEMO / "docker-compose.yml").read_text(encoding="utf-8"),
            (DEMO / "docker-compose.gb10.yml").read_text(encoding="utf-8"))


def test_every_dockerfile_from_is_digest_pinned_and_every_pip_install_is_constrained():
    for name, text in _texts()[0].items():
        check_dockerfile(name, text)


# the approver closure as resolved on 2026-10-29 (C-323); a change is made on purpose, with a compose-smoke run
APPROVER_PINS = {
    "anthropic": "2.3.0", "docstring_parser": "0.18.0", "httpcore2": "2.16.0", "httpx2": "2.16.0",
    "jiter": "0.18.0", "sniffio": "1.3.1", "truststore": "0.10.5",
}
PIN_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*==[0-9][A-Za-z0-9_.+!-]*$")


def check_constraints(text: str) -> None:
    pins: dict[str, str] = {}
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        assert PIN_LINE.match(ln.strip()), f"constraint is not an exact name==version: {ln!r}"
        name, _, version = ln.strip().partition("==")
        pins[name] = version
    for name, version in APPROVER_PINS.items():
        assert pins.get(name) == version, f"{name}: pinned {pins.get(name)!r}, expected {version!r}"


def test_the_constraints_file_pins_the_approver_dependencies_exactly():
    check_constraints((ROOT / "integration" / "constraints.txt").read_text(encoding="utf-8"))


def test_every_compose_service_is_hardened_digest_pinned_and_probes_its_own_port():
    _, base, gb10 = _texts()
    check_compose(base, gb10)
    services = _services(base, gb10)
    # the six that were unhardened before C-323
    for name in ("approver", "witness", "canary-agent", "manifests-admin", "keys-admin", "attest-keys-admin"):
        assert name in services, name


# --- mutants: each must turn a check RED -------------------------------------------------------

def _drop_digest(t: str) -> str:
    return re.sub(r"(FROM python:3\.12-slim)@sha256:[0-9a-f]+", r"\1", t, count=1)


DOCKER_MUTANTS = {
    "a base image loses its digest": ("integration/demo/Dockerfile", _drop_digest),
    "the approver pip install loses its constraint": (
        "services/claude-approver/Dockerfile", lambda t: t.replace("-c integration/constraints.txt", "", 1)),
    "the fly pip install loses its constraint": (
        "integration/fly/Dockerfile", lambda t: t.replace("-c integration/constraints.txt", "", 1)),
}


DOCKER_MUTANTS["the fly caddy COPY --from loses its digest"] = (
    "integration/fly/Dockerfile", lambda t: re.sub(r"(COPY --from=caddy:[^@\s]+)@sha256:[0-9a-f]+", r"\1", t, count=1))


@pytest.mark.parametrize("name", sorted(DOCKER_MUTANTS))
def test_each_dockerfile_mutant_turns_the_check_red(name: str):
    which, mutate = DOCKER_MUTANTS[name]
    text = _texts()[0][which]
    mutated = mutate(text)
    assert mutated != text, f"mutant {name!r} changed nothing"
    with pytest.raises(AssertionError):
        check_dockerfile(which, mutated)


COMPOSE_MUTANTS = {
    "the approver loses the hardening anchor": (0, lambda t: t.replace("    <<: *svc\n    profiles: [approver]", "    profiles: [approver]", 1)),
    "a service's cap_drop is removed": (0, lambda t: t.replace("  cap_drop: [ALL]\n", "", 1)),
    "the sentinel healthcheck probes another port": (
        0, lambda t: t.replace("127.0.0.1:8004/health", "127.0.0.1:8040/health", 1)),
    "the proxy image loses its digest": (0, lambda t: re.sub(r"(image: caddy:2-alpine)@sha256:[0-9a-f]+", r"\1", t, count=1)),
    "the witness loses the hardening": (1, lambda t: t.replace("  witness:\n    <<: *hardened\n", "  witness:\n", 1)),
    "the canary loses the hardening": (1, lambda t: t.replace("  canary-agent:\n    <<: *hardened\n", "  canary-agent:\n", 1)),
    "a keys-admin root is writable again": (
        1, lambda t: t.replace("  read_only: true\n  tmpfs: [/tmp]\n", "  tmpfs: [/tmp]\n", 1)),
}


def _in_gb10_registry(extra: str):
    """Add `extra` (indented keys of the registry service) right under `  registry:` in the GB10 file."""
    return lambda base, gb10: (base, gb10.replace("  registry:\n", "  registry:\n" + extra, 1))


def _top_volume(device: str):
    return lambda base, gb10: (base, gb10.replace(
        "  field-manifests:\n", "  evil:\n    driver: local\n    driver_opts: {type: none, o: bind, device: '" + device + "'}\n  field-manifests:\n", 1))


PAIR_MUTANTS = {
    "a GB10 cap_drop: !reset [] removes the base hardening": _in_gb10_registry("    cap_drop: !reset []\n"),
    "a GB10 security_opt: !reset [] removes the base hardening": _in_gb10_registry("    security_opt: !reset []\n"),
    "a GB10 read_only: !reset null removes the base hardening": _in_gb10_registry("    read_only: !reset null\n"),
    "a GB10 network_mode: host": _in_gb10_registry("    network_mode: host\n"),
    "a GB10 pid: host": _in_gb10_registry("    pid: host\n"),
    "a GB10 ipc: host": _in_gb10_registry("    ipc: host\n"),
    "a GB10 device is passed in": _in_gb10_registry("    devices: [/dev/kmsg]\n"),
    "a GB10 seccomp=unconfined": _in_gb10_registry("    security_opt: [seccomp=unconfined]\n"),
    # the registry already has a `volumes:` list in the GB10 file; a second key would be a duplicate, so extend it
    "a GB10 host root bind spelled //": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '//:/h'\n", gb10, count=1)),
    "a GB10 host root bind spelled /./": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/./:/h'\n", gb10, count=1)),
    "a GB10 host root bind in the long syntax": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)",
        r"\1      - {type: bind, source: /, target: /h}\n", gb10, count=1)),
    "a GB10 host root bind in the long syntax spelled //": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)",
        r"\1      - {type: bind, source: '//', target: /h}\n", gb10, count=1)),
    "a GB10 bind of /etc/shadow": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/etc/shadow:/h:ro'\n", gb10, count=1)),
    "a GB10 bind of /etc/ssh": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/etc/ssh:/h:ro'\n", gb10, count=1)),
    "a GB10 bind of /root": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/root:/h:ro'\n", gb10, count=1)),
    "a GB10 bind of /dev/mem": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/dev/mem:/h'\n", gb10, count=1)),
    "a GB10 bind of /var/lib/docker/volumes": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/var/lib/docker/volumes:/h'\n", gb10, count=1)),
    "a GB10 bind of the whole /home": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/home:/h'\n", gb10, count=1)),
    "a GB10 bind whose environment default is the root": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '${HOSTDIR:-/}:/h'\n", gb10, count=1)),
    "a GB10 bind of /etc": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/etc:/h:ro'\n", gb10, count=1)),
    "a GB10 bind of /proc": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/proc:/h:ro'\n", gb10, count=1)),
    "a GB10 host root bind": lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '/:/host'\n", gb10, count=1)),
    # C-402: the sources the first lists missed, as registry binds; and a named volume bound through driver_opts
    **{f"a GB10 bind of {src}": (lambda s: lambda base, gb10: (base, re.sub(
        r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '" + s + ":/h'\n", gb10, count=1)))(src)
       for src in ("/run", "/run/podman/podman.sock", "/run/containerd/containerd.sock", "/var/lib", "/var/lib/containerd",
                   "/var/lib/kubelet", "/home/spinner/.ssh", "/home/spinner/.aws", "/home/spinner/.docker",
                   "${A:-${B:-/}}", "${X:+/}", "${X:=/}", "../../..", "./../../../etc", "~/.ssh", "/srv/x/crio.sock")},
    "a GB10 named volume bound to / through driver_opts": _top_volume("/"),
    "a GB10 named volume bound to /etc through driver_opts": _top_volume("/etc"),
    # the base file adds a capability and the GB10 file "restates" the list: compose appends, so SYS_ADMIN stays
    "a GB10 cap_add does not hide a base cap_add": lambda base, gb10: (
        base.replace("  registry:\n    <<: *svc\n", "  registry:\n    <<: *svc\n    cap_add: [SYS_ADMIN]\n", 1),
        gb10.replace("  registry:\n", "  registry:\n    cap_add: [DAC_READ_SEARCH]\n", 1)),
    "a GB10 override adds a capability to a base service": lambda base, gb10: (
        base, gb10.replace("  registry:\n", "  registry:\n    cap_add: [SYS_ADMIN]\n", 1)),
    "a GB10 override makes a base service privileged": lambda base, gb10: (
        base, gb10.replace("  registry:\n", "  registry:\n    privileged: true\n", 1)),
    "a GB10 override mounts the docker socket into a base service": lambda base, gb10: (
        base, re.sub(r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)",
                     r"\1      - /var/run/docker.sock:/var/run/docker.sock\n", gb10, count=1)),
}


@pytest.mark.parametrize("name", sorted(PAIR_MUTANTS))
def test_each_pair_mutant_turns_the_check_red(name: str):
    _, base, gb10 = _texts()
    mb, mg = PAIR_MUTANTS[name](base, gb10)
    assert (mb, mg) != (base, gb10), f"mutant {name!r} changed nothing"
    with pytest.raises(AssertionError):
        check_compose(mb, mg)


def test_compose_merge_appends_lists_merges_maps_and_honours_override():
    base = {"a": [1], "m": {"x": 1, "y": 2}, "s": "old", "o": [1, 2]}
    over = {"a": [2], "m": {"y": 3}, "s": "new", "o": _Override([9])}
    assert _merge(base, over) == {"a": [1, 2], "m": {"x": 1, "y": 3}, "s": "new", "o": [9]}


def test_compose_merge_removes_a_reset_key_and_replaces_command_entrypoint_and_healthcheck_test():
    base = {"cap_drop": ["ALL"], "command": ["a", "--port", "1"], "entrypoint": ["x"],
            "healthcheck": {"test": ["CMD", "a"], "interval": "10s"}, "security_opt": ["no-new-privileges:true"]}
    over = {"cap_drop": _Reset([]), "command": ["b"], "entrypoint": ["y"],
            "healthcheck": {"test": ["CMD", "b"]}, "security_opt": _Reset(None)}
    merged = _merge(base, over)
    assert "cap_drop" not in merged and "security_opt" not in merged
    assert merged["command"] == ["b"] and merged["entrypoint"] == ["y"]
    assert merged["healthcheck"] == {"test": ["CMD", "b"], "interval": "10s"}


@pytest.mark.parametrize("source,forbidden", [
    ("/", True), ("//", True), ("/etc", True), ("/etc/shadow", True), ("/etc/ssh/", True), ("/proc/1/root", True),
    ("/sys/fs/cgroup", True), ("/var/lib/docker/volumes", True), ("/var/run/docker.sock", True), ("/root", True),
    ("/root/.ssh", True), ("/dev", True), ("/dev/mem", True), ("/boot", True), ("/home", True), ("/var", True),
    ("/usr", True), ("${X:-/}", True), ("${X:-/etc}/ssh", True), ("${X-/}", True), ("/etc/../etc/shadow", True),
    ("/home/spinner/.field-local/caller-keys/registry", False), ("${KEYS:-/home/spinner/.field-local/caller-keys}/w", False),
    ("/var/log/app", False), ("/usr/share/zoneinfo", False), ("/opt/field/data", False), ("./operators", False),
    ("field-data", False), ("${FIELD_OPERATORS_DIR:-./operators}", False), ("${NO_DEFAULT}", False),
])
def test_the_forbidden_bind_sources_are_trees_or_exact_paths_as_stated(source, forbidden):
    assert _binds_forbidden_host_path(source) is forbidden, source


# C-402 (reviewer C-399 F-C399-1/-2): sources the first lists missed, and the pins that stopped short.
@pytest.mark.parametrize("source", [
    "/run", "/run/", "/run/user/1000", "/var/run", "/var/run/user/1000", "/var/run/anything", "/run/containerd/containerd.sock", "/run/podman/podman.sock",
    "/var/run/crio/crio.sock", "/var/lib", "/var/lib/", "/var/lib/containerd", "/var/lib/containerd/io.containerd",
    "/var/lib/kubelet", "/var/lib/kubelet/pods", "/home/spinner/.ssh", "/home/spinner/.ssh/id_ed25519",
    "/home/spinner/.aws", "/home/spinner/.aws/credentials", "/home/spinner/.docker", "/home/spinner/.docker/config.json",
    "/srv/x/containerd.sock", "/opt/y/podman.sock", "/tmp/crio.sock", "/tmp/docker.sock", "/tmp/cri-dockerd.sock",
])
def test_the_host_runtime_and_credential_paths_the_first_lists_missed_are_forbidden(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", ["/lib", "/bin", "/sbin", "/opt", "/srv", "/mnt", "/media", "/home", "/var", "/usr"])
def test_every_exact_entry_is_forbidden_on_its_own_and_not_below_it(source):
    assert _binds_forbidden_host_path(source) is True
    # one level below: fine, except /home/<user> which is a home directory itself (C-426)
    assert _binds_forbidden_host_path(source + "/field") is (source == "/home")
    assert _binds_forbidden_host_path(source + "/field/data") is False


@pytest.mark.parametrize("source", [
    "${A:-${B:-/}}", "${A:-${B:-${C:-/etc}}}", "${X:+/}", "${X+/}", "${X:=/}", "${X=/}", "${X:+/etc}/ssh",
    "${HOST_DIR2:-/}", "${h:-/}", "${A:-}${B:-/}",
])
def test_every_default_and_replacement_spelling_of_a_forbidden_path_is_expanded(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", ["../../..", "../../../etc", "./../../../etc", "./a/../../../..", "~", "~/", "~/.ssh", "~root/x"])
def test_a_source_that_climbs_out_of_the_repository_or_names_a_home_is_forbidden(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", [
    "/etcetera", "/devices", "/runtime", "/run-keys", "/bootstrap", "/rootfs", "/procfs", "/system", "/var/lib/field",
    "/var/lib/docker-field", "/home/spinner/ssh", "/home/spinner/.ssh-keys-local", "/home/spinner/.field-local/keys",
    "/home/spinner/.docker.d", "/srv-data", "/tmp/dockersock", "/tmp/not-docker.sock.d", "/tmp/mydocker.sock",
    ".", "./", "./operators", "./a/../b", "./a/b/..", "..", "../../manifests", "./../../etc", "../../services/x", "./a/b/../../..", "operators", "field-data", "${NO_DEFAULT}", "$HOSTDIR", "${NO_DEFAULT}/x",
    None, 5,
])
def test_paths_beside_the_forbidden_ones_and_unresolvable_variables_are_not_forbidden(source):
    """The boundary of each rule: a tree is its path and what is under it (`/etcetera` is not `/etc`), a variable
    with no default is unknown and left alone (the estate's .env decides), a sourceless long-syntax volume is fine."""
    assert _binds_forbidden_host_path(source) is False, source


def test_a_sourceless_long_syntax_volume_is_accepted_by_the_whole_check():
    _, base, gb10 = _texts()
    mb, mg = _in_gb10_registry("    tmpfs: [/tmp, /scratch]\n")(base, gb10)
    mg = re.sub(r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - {type: tmpfs, target: /scratch2}\n", mg, count=1)
    assert (mb, mg) != (base, gb10)
    check_compose(mb, mg)


@pytest.mark.parametrize("volume,short", [
    ("${A:-${B:-/}}:/h", "${A:-${B:-/}}"), ("${A:+/etc}/x:/h:ro", "${A:+/etc}/x"), ("${X:=/}:/h", "${X:=/}"),
])
def test_the_host_side_of_a_nested_or_replacement_default_stays_whole(volume, short):
    assert _short_source(volume) == short


@pytest.mark.parametrize("device", ["/", "/etc", "/run/podman/podman.sock", "/var/lib", "/home/spinner/.ssh", "${D:-/}", "../../.."])
def test_a_named_volume_that_binds_a_forbidden_host_directory_through_driver_opts_is_red(device):
    _, base, gb10 = _texts()
    mb, mg = _top_volume(device)(base, gb10)
    assert (mb, mg) != (base, gb10)
    with pytest.raises(AssertionError, match="volume evil: binds a host path"):
        check_compose(mb, mg)


def test_a_named_volume_that_binds_a_fine_host_directory_through_driver_opts_is_green():
    _, base, gb10 = _texts()
    mb, mg = _top_volume("/opt/field/data/ledger")(base, gb10)
    assert (mb, mg) != (base, gb10)
    check_compose(mb, mg)


@pytest.mark.parametrize("volume,short", [
    ("/etc/ssh:/h:ro", "/etc/ssh"), ("${X:-/}:/h", "${X:-/}"), ("${KEYS:-/home/a}/w:/run/k:ro", "${KEYS:-/home/a}/w"),
    ("field-data:/data", "field-data"), ("./operators:/o:ro", "./operators"),
])
def test_the_host_side_of_a_volume_string_keeps_a_default_expression_whole(volume, short):
    assert _short_source(volume) == short


@pytest.mark.parametrize("source,normal", [
    ("/", "/"), ("//", "/"), ("/./", "/"), ("/.", "/"), ("/..", "/"), ("/a/..", "/"), ("//etc/", "/etc"),
    ("/etc/./", "/etc"), ("/var/lib/docker/", "/var/lib/docker"), ("./operators", "./operators"), ("field-data", "field-data"),
])
def test_the_bind_source_is_normalised(source, normal):
    assert _normal_root(source) == normal


def test_a_service_level_reset_removes_the_service():
    """F-C360-3: `registry: !reset null` in the later file drops the whole service (it is not merged, and it
    does not leave a half service for the checks to trip over)."""
    base = "services:\n  a: {image: 'x@sha256:1'}\n  b: {image: 'y@sha256:1'}\n"
    over = "services:\n  a: !reset null\n"
    assert set(_services(base, over)) == {"b"}


def _gb10_with_the_proxy_reset(gb10: str) -> str:
    """The real GB10 file with ONLY the proxy service replaced by `proxy: !reset null` (its whole block removed),
    so nothing but the reset differs (C-391, reviewer C-371 F-C371-1: the first version renamed the block to a
    placeholder service, which tripped an unrelated check and hid whether the reset was the cause)."""
    start = gb10.index("\n  proxy:\n")
    end = gb10.index("\n  manifests-admin:\n")
    return gb10[:start] + "\n  proxy: !reset null" + gb10[end:]


def test_the_real_gb10_file_with_the_proxy_service_reset_is_caught():
    """The proxy is the one service READ_ONLY_EXEMPT names: resetting it away makes that exemption stale, and
    that is the ONLY thing red (the message names it)."""
    _, base, gb10 = _texts()
    mutated = _gb10_with_the_proxy_reset(gb10)
    assert mutated != gb10 and "proxy: !reset null" in mutated
    assert "proxy" not in _services(base, mutated)            # the reset really removed the service
    with pytest.raises(AssertionError, match="no longer exists"):
        check_compose(base, mutated)


def test_a_reset_on_a_new_service_key_is_dropped():
    assert _unwrap({"a": _Reset([]), "b": [1]}) == {"b": [1]}


def test_the_gb10_proxy_override_replaces_the_base_ports_and_volumes():
    """`!override` in the GB10 file really replaces (the real file, through the same merge)."""
    _, base, gb10 = _texts()
    proxy = _services(base, gb10)["proxy"]
    assert proxy["ports"] == ["18080:8080", "18443:8443"]
    assert not any("./Caddyfile:/etc/caddy/Caddyfile:ro" == v for v in proxy["volumes"])


COMPOSE_MUTANTS.update({
    "tmpfs removed while the root stays read-only": (
        0, lambda t: t.replace("  tmpfs: [/tmp]\n", "", 1)),
    "a hardened service adds SYS_ADMIN back": (
        0, lambda t: t.replace("  cap_add: [DAC_READ_SEARCH]\n", "  cap_add: [DAC_READ_SEARCH, SYS_ADMIN]\n", 1)),
    "the canary adds a capability back": (
        1, lambda t: t.replace("  canary-agent:\n    <<: *hardened\n", "  canary-agent:\n    <<: *hardened\n    cap_add: [NET_RAW]\n", 1)),
    "a service is privileged": (
        0, lambda t: t.replace("  cap_drop: [ALL]\n", "  cap_drop: [ALL]\n  privileged: true\n", 1)),
    "a service mounts the docker socket": (
        1, lambda t: t.replace("      - field-keys:/data/keys:ro\n", "      - field-keys:/data/keys:ro\n"
                               "      - /var/run/docker.sock:/var/run/docker.sock\n", 1)),
})


CONSTRAINT_MUTANTS = {
    "anthropic loosened to >=": lambda t: t.replace("anthropic==2.3.0", "anthropic>=2.3.0", 1),
    "anthropic version changed": lambda t: t.replace("anthropic==2.3.0", "anthropic==2.9.9", 1),
    "a pin loses its version": lambda t: t.replace("jiter==0.18.0", "jiter", 1),
    "an approver pin is dropped": lambda t: t.replace("sniffio==1.3.1\n", "", 1),
}


@pytest.mark.parametrize("name", sorted(CONSTRAINT_MUTANTS))
def test_each_constraints_mutant_turns_the_check_red(name: str):
    text = (ROOT / "integration" / "constraints.txt").read_text(encoding="utf-8")
    mutated = CONSTRAINT_MUTANTS[name](text)
    assert mutated != text, f"mutant {name!r} changed nothing"
    with pytest.raises(AssertionError):
        check_constraints(mutated)


@pytest.mark.parametrize("name", sorted(COMPOSE_MUTANTS))
def test_each_compose_mutant_turns_the_check_red(name: str):
    which, mutate = COMPOSE_MUTANTS[name]
    _, base, gb10 = _texts()
    pair = [base, gb10]
    mutated = mutate(pair[which])
    assert mutated != pair[which], f"mutant {name!r} changed nothing"
    pair[which] = mutated
    with pytest.raises(AssertionError):
        check_compose(*pair)


# --- C-426 (reviewer C-424 F-C424-1/-2/-3) ----------------------------------------------------------------------------


@pytest.mark.parametrize("source", [
    "/home/spinner", "/home/spinner/", "/home//spinner", "/home/./spinner", "/home/spinner/x/..",
    "/home/spinner/.gnupg", "/home/spinner/.kube/config", "/home/spinner/.config/gcloud", "/home/spinner/.config/gcloud/creds.db",
    "/home/spinner/.git-credentials", "/home/spinner/.netrc", "/home/spinner/.npmrc", "/home/spinner/.azure",
    "/home/spinner/.local/share/keyrings", "${HOME}", "$HOME", "${HOME}/.ssh", "$HOME/.ssh", "${HOME}/.aws/credentials",
    "${HOME:-/root}/.ssh", "../..", "../../.git", "../../.git/config", "../../.env", "./.env", "./sub/.env", "../../.env.local",
    "/tmp/buildkitd.sock", "/tmp/dockershim.sock", "/tmp/cri-o.sock", "/var/lib/lxd", "/var/lib/lxc/x", "/var/lib/rancher",
    "/var/lib/k0s", "/var/lib/etcd", "/var/lib/snapd",
])
def test_the_parents_and_the_other_credential_places_of_a_forbidden_path_are_forbidden(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", [
    # (C-442: `/home/spinner/.config` itself is no longer here: the parent of a credential tree is forbidden exactly)
    "/home/spinner/x", "/home/spinner/x/.ssh", "/home/a/b/.ssh", "/home/spinner/.config/app",
    "/home/spinner/.local/share/app", "/home/spinner/.gnupg-notes", "${HOME}/data", "$HOME/data", "$HOMEDIR", "${HOMEDIR}",
    "/tmp/docker.sock.d", "/tmp/buildkitd.sock.d", "/var/lib/lxdata", "../../.github", "../../.envrc", "../../.envrc-docs/x", "./environment",
    "../../envs/.env.d/x/y", "./a/b/../../..", "${A:-${B:-${C:-${D:-./operators}}}}",
])
def test_paths_beside_those_are_still_not_forbidden(source):
    assert _binds_forbidden_host_path(source) is False, source


def test_a_four_level_nested_default_expands_to_the_root():
    assert _binds_forbidden_host_path("${A:-${B:-${C:-${D:-/}}}}") is True


def test_a_forbidden_device_in_the_base_files_volumes_is_red():
    _, base, gb10 = _texts()
    mb = base.replace("\nvolumes:\n  field-data:", "\nvolumes:\n  evil:\n    driver_opts: {type: none, o: bind, device: /etc}\n  field-data:", 1)
    assert mb != base
    with pytest.raises(AssertionError, match="volume evil: binds a host path"):
        check_compose(mb, gb10)


def test_a_gb10_override_of_a_base_volume_merges_with_it_key_by_key():
    """The base file binds a forbidden device and the GB10 file only adds a label: compose merges the maps, so the
    device stays and the check is red; an override that REPLACES the device with a fine one is green."""
    _, base, gb10 = _texts()
    mb = base.replace("\nvolumes:\n  field-data:", "\nvolumes:\n  evil:\n    driver_opts: {type: none, o: bind, device: /etc}\n  field-data:", 1)
    label = gb10.replace("\nvolumes:\n", "\nvolumes:\n  evil:\n    labels: {a: b}\n", 1)
    assert label != gb10
    with pytest.raises(AssertionError, match="volume evil: binds a host path"):
        check_compose(mb, label)
    fixed = gb10.replace("\nvolumes:\n", "\nvolumes:\n  evil:\n    driver_opts: {device: /opt/field/data}\n", 1)
    check_compose(mb, fixed)


def test_a_gb10_reset_of_a_base_volume_removes_it():
    _, base, gb10 = _texts()
    mb = base.replace("\nvolumes:\n  field-data:", "\nvolumes:\n  evil:\n    driver_opts: {type: none, o: bind, device: /etc}\n  field-data:", 1)
    reset = gb10.replace("\nvolumes:\n", "\nvolumes:\n  evil: !reset null\n", 1)
    assert reset != gb10
    check_compose(mb, reset)


@pytest.mark.parametrize("src", [
    "/home/spinner", "/home/spinner/.gnupg", "/home/spinner/.kube", "${HOME}", "$HOME/.ssh", "../..", "../../.git", "./.env",
    "/tmp/buildkitd.sock", "/var/lib/rancher",
])
def test_a_registry_bind_of_each_new_source_is_red(src):
    _, base, gb10 = _texts()
    mb, mg = (base, re.sub(r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '" + src + ":/h'\n", gb10, count=1))
    assert (mb, mg) != (base, gb10)
    with pytest.raises(AssertionError):
        check_compose(mb, mg)


# --- C-435 (reviewer C-434 F-C434-1/-2/-3/-4) --------------------------------------------------------------------------


@pytest.mark.parametrize("source", [
    "${HOME:-/tmp}/.ssh", "${HOME:-}/.ssh", "${HOME-/tmp}/.ssh", "${HOME:+/x}/.ssh", "${HOME:?}/.ssh", "${HOME:=/tmp}/.ssh",
    "${HOME:-${X:-/tmp}}/.ssh", "${HOME:-/tmp}", "${HOME-}", "${HOME:?err}", "${HOME:-/tmp}/.config/gh", "$HOME",
    "${XDG_RUNTIME_DIR}", "${XDG_RUNTIME_DIR}/docker.sock", "${XDG_RUNTIME_DIR:-/tmp}/x", "${SSH_AUTH_SOCK}", "$SSH_AUTH_SOCK",
    "${SSH_AUTH_SOCK:-/tmp/agent}", "${XDG_CONFIG_HOME}/gcloud", "${XDG_CONFIG_HOME:-/tmp}/gcloud/x", "${DOCKER_HOST}", "$DOCKER_HOST",
    "${DOCKER_HOST:-/tmp/x}",
])
def test_a_variable_with_a_settled_meaning_is_read_as_its_value_whatever_its_default(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", [
    "/home/spinner/.config/gh", "/home/spinner/.config/rclone/rclone.conf", "/home/spinner/.pgpass", "/home/spinner/.my.cnf",
    "/home/spinner/.vault-token", "/home/spinner/.s3cfg", "/home/spinner/.boto", "/home/spinner/.oci", "/home/spinner/.terraform.d",
    "/home/spinner/.pypirc", "/home/spinner/.cargo", "/home/spinner/.cargo/registry", "/home/spinner/.m2", "/home/spinner/.gradle",
    "/home/spinner/.password-store", "/home/spinner/.bash_history", "/home/spinner/.mozilla", "/home/spinner/.pki",
    "/tmp/dockerd.sock", "/tmp/nerdctl.sock", "/tmp/rootlesskit.sock", "/tmp/k3s.sock", "/tmp/kubelet.sock", "/tmp/containerd-shim.sock",
    "/var/lib/containers", "/var/lib/podman/x", "/var/lib/libvirt", "/var/lib/k3s", "/var/lib/microk8s", "/var/lib/kubernetes",
    "/var/lib/cni", "/var/lib/buildkit", "/var/lib/nerdctl",
])
def test_the_credential_places_runtime_sockets_and_state_one_step_further_out_are_forbidden(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("source", [
    "$HOMEDIR", "${HOMEDIR}", "$HOME_DIR", "${HOME_DIR}", "${HOME_DIR:-./operators}", "${HOMEDIR:-/opt/field/data}", "$SSH_AUTH_SOCKET",
    "${XDG_RUNTIME_DIR_X:-./a}", "${MYHOME:-./a}", "/home/spinner/.config/app", "/home/spinner/.cargo-notes", "/home/spinner/.m2x",
    "/tmp/kubelet.sock.d", "/var/lib/containersx", "/var/lib/cnis",
])
def test_names_and_paths_that_only_resemble_the_settled_ones_are_not_forbidden(source):
    assert _binds_forbidden_host_path(source) is False, source


def test_a_registry_bind_that_gives_home_a_default_is_red():
    _, base, gb10 = _texts()
    mg = re.sub(r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", r"\1      - '${HOME:-/tmp}/.ssh:/h:ro'\n", gb10, count=1)
    assert mg != gb10
    with pytest.raises(AssertionError, match="binds a host path it must not"):
        check_compose(base, mg)


def test_a_top_level_volume_device_that_gives_home_a_default_is_red():
    _, base, gb10 = _texts()
    mg = gb10.replace("\nvolumes:\n", "\nvolumes:\n  evil:\n    driver_opts: {type: none, o: bind, device: '${HOME:-/tmp}/.ssh'}\n", 1)
    assert mg != gb10
    with pytest.raises(AssertionError, match="volume evil: binds a host path"):
        check_compose(base, mg)


def test_a_null_override_of_a_base_volume_keeps_the_base_definition():
    """Compose's treatment of `name:` (null) over a mapping is not documented: the stricter reading is kept."""
    _, base, gb10 = _texts()
    mb = base.replace("\nvolumes:\n  field-data:", "\nvolumes:\n  evil:\n    driver_opts: {type: none, o: bind, device: /etc}\n  field-data:", 1)
    nulled = gb10.replace("\nvolumes:\n", "\nvolumes:\n  evil:\n", 1)
    assert nulled != gb10
    with pytest.raises(AssertionError, match="volume evil: binds a host path"):
        check_compose(mb, nulled)


# ------------------------------------------------ C-442 (reviewers C-441, Lane 5 and Lane 4)

NEW_CREDENTIAL_PLACES = [
    ".config/git", ".config/git/credentials", ".config/helm", ".config/doctl", ".config/op", ".config/1Password",
    ".config/containers", ".config/containers/auth.json", ".config/sops", ".config/age", ".age", ".terraformrc",
    ".gitconfig", ".gcloud", ".helm", ".minikube", ".ansible", ".dockercfg", ".credentials", ".secrets", ".ssh2",
    ".pg_service.conf", ".mongorc.js", ".1password", ".python_history", ".zsh_history", ".history", ".rediscli_history",
    ".psql_history", ".mysql_history",
]


@pytest.mark.parametrize("place", NEW_CREDENTIAL_PLACES)
def test_the_further_credential_places_are_forbidden_by_path_and_through_home(place):
    assert _binds_forbidden_host_path("/home/spinner/" + place) is True, place
    assert _binds_forbidden_host_path("${HOME}/" + place) is True, place


@pytest.mark.parametrize("parent", [
    "${HOME}/.config", "$HOME/.config", "/home/spinner/.config", "/home/spinner/.config/", "/home/spinner/./.config",
    "/home/spinner/.local", "/home/spinner/.local/share", "${HOME}/.local/share", "${HOME:-/tmp}/.local",
    "${XDG_CONFIG_HOME}", "${XDG_CONFIG_HOME:-/x}", "/home/spinner/.config/git",
])
def test_the_parent_of_a_credential_tree_is_forbidden_exactly(parent):
    assert _binds_forbidden_host_path(parent) is True, parent


@pytest.mark.parametrize("fine", [
    "/home/spinner/.config/myapp", "/home/spinner/.local/bin", "/home/spinner/.local/share/applications",
    "/home/spinner/.configuration", "/home/spinner/.local-data", "/home/spinner/.histories", "/home/spinner/.agent",
])
def test_a_directory_beside_or_below_a_parent_that_is_not_listed_stays_legal(fine):
    assert _binds_forbidden_host_path(fine) is False, fine


@pytest.mark.parametrize("source", [
    "${PWD}", "$PWD", "${PWD}/", "${PWD}/.git", "${PWD}/.git/config", "${PWD}/.env", "${PWD}/..", "${PWD}/../..",
    "${PWD}/../../..", "${PWD}/../../../.git", "${OLDPWD}", "$OLDPWD/..", "${PWD:-/x}", "${PWD-/x}", "${PWD:?}", "${PWD:+/x}",
])
def test_pwd_and_oldpwd_are_read_as_the_repository_root_and_a_climb_from_it_is_refused(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("fine", ["${PWD}/manifests", "$PWD/integration/demo/Caddyfile", "${PWD}/services/x/data", "${PWD2}", "${PWDX}/x"])
def test_a_path_inside_the_repository_below_pwd_and_a_longer_variable_name_stay_legal(fine):
    assert _binds_forbidden_host_path(fine) is False, fine


@pytest.mark.parametrize("source", [
    "${GNUPGHOME}", "$GNUPGHOME", "${GNUPGHOME}/x", "${GNUPGHOME:-/x}", "${KUBECONFIG}", "$KUBECONFIG", "${DOCKER_CONFIG}/config.json",
    "${AWS_SHARED_CREDENTIALS_FILE}", "${GOOGLE_APPLICATION_CREDENTIALS}", "${KRB5CCNAME}", "${HISTFILE}", "${XDG_DATA_HOME}",
    "${XDG_STATE_HOME}", "${XDG_CACHE_HOME}", "${CONTAINER_HOST}",
])
def test_a_variable_that_names_a_credential_location_is_refused_as_a_bind_source(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("fine", ["${GNUPGHOME2}", "${GNUPGHOMEX}/x", "$KUBECONFIGS", "${DOCKER_CONFIGS}", "${HISTFILESIZE}"])
def test_a_longer_variable_name_is_not_a_credential_variable(fine):
    assert _binds_forbidden_host_path(fine) is False, fine


@pytest.mark.parametrize("source", ["${DATA_DIR}/.ssh", "${A}/.ssh/id_ed25519", "$A/.aws", "${A}/.config", "${A}/.local/share",
                                    "${B}/.gnupg", "$C/.kube/config", "${A}/.config/git/credentials"])
def test_an_unresolved_variable_with_a_credential_tail_is_refused(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("fine", ["${A}/data", "${A}/.cache", "$B/field/keys", "${NO_DEFAULT}/x", "${A}/.config/myapp"])
def test_an_unresolved_variable_with_an_ordinary_tail_stays_legal(fine):
    """Decision: the value of a variable with no known meaning is the estate's .env's to decide; only a credential tail
    after it is refused."""
    assert _binds_forbidden_host_path(fine) is False, fine


@pytest.mark.parametrize("source", [
    "/tmp/libpod.sock", "/run/x/docker-rootless.sock", "/tmp/isulad.sock", "/tmp/cri-docker.sock", "/tmp/agent.sock",
    "/tmp/ssh-agent.sock", "/tmp/gpg-agent.sock", "/tmp/S.gpg-agent", "/tmp/S.gpg-agent.extra", "/tmp/snapd.socket",
    "/tmp/lxd.socket", "/var/lib/crio", "/var/lib/crio/storage",
])
def test_more_runtime_sockets_and_the_crio_state_are_forbidden(source):
    assert _binds_forbidden_host_path(source) is True, source


@pytest.mark.parametrize("fine", ["/tmp/myagent.sock", "/tmp/agent.sock.d", "/tmp/S.gpg-agentx", "/tmp/mylxd.socket", "/var/lib/crio-field"])
def test_a_name_that_only_ends_like_a_socket_is_not_one(fine):
    assert _binds_forbidden_host_path(fine) is False, fine


@pytest.mark.parametrize("operator", ["?", "+/x", "=/tmp", ":?", ":+/x", ":=/tmp", "-/tmp", ":-/tmp", ":-${X:-/tmp}", "-${X-/tmp}"])
def test_every_operator_of_a_settled_variable_reads_as_the_variable_itself(operator):
    assert _binds_forbidden_host_path("${HOME" + operator + "}/.ssh") is True, operator
    assert _binds_forbidden_host_path("${HOME" + operator + "}") is True, operator        # the home directory itself


def test_the_settled_variable_reader_counts_nested_braces():
    """The leftover `}` of a nested default would not change a verdict, so the reader itself is pinned."""
    assert _read_settled_variables("${HOME:-${X:-/tmp}}/a") == "/home/_user/a"
    assert _read_settled_variables("${HOME:-${X:-${Y:-/t}}}/a") == "/home/_user/a"
    assert _read_settled_variables("${HOME:-${X:-/tmp}") == "${HOME:-${X:-/tmp}"       # unbalanced: left alone


@pytest.mark.parametrize("source", ["$HOME2/.ssh", "${HOME2}/.ssh", "$HOME_DIR", "${HOME_DIR}/.ssh", "$HOMEDIR", "$HOME_", "${HOME1:-/x}"])
def test_a_longer_variable_name_is_not_read_as_home(source):
    assert _read_settled_variables(source) == source


def test_a_bare_home_variable_is_read_as_home_with_and_without_braces():
    assert _read_settled_variables("$HOME/a") == "/home/_user/a" and _read_settled_variables("${HOME}/a") == "/home/_user/a"


REGISTRY_BIND_MUTANTS = [
    "${HOME}/.config:/h:ro", "/home/spinner/.local/share:/h", "${HOME}/.config/git:/h", "/home/spinner/.terraformrc:/h",
    "${PWD}/..:/h", "${PWD}:/h", "${GNUPGHOME}:/h", "${A}/.ssh:/h", "/tmp/libpod.sock:/h", "/var/lib/crio:/h",
    "${HOME?}/.ssh:/h", "${HOME+/x}/.ssh:/h", "${HOME=/tmp}/.ssh:/h",
]


@pytest.mark.parametrize("volume", REGISTRY_BIND_MUTANTS)
def test_each_of_these_binds_in_the_gb10_registry_turns_the_whole_check_red(volume):
    _, base, gb10 = _texts()
    mutated = re.sub(r"(\n  registry:\n(?:    (?:#|<<)[^\n]*\n)*    volumes:\n)", lambda m: m.group(1) + "      - '" + volume + "'\n",
                     gb10, count=1)
    assert mutated != gb10
    with pytest.raises(AssertionError):
        check_compose(base, mutated)
