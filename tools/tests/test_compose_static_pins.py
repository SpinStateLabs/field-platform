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
FORBIDDEN_BIND_TREES = ("/etc", "/proc", "/sys", "/var/lib/docker", "/var/run", "/root", "/dev", "/boot")
FORBIDDEN_BIND_EXACT = {"/", "/home", "/var", "/usr", "/lib", "/bin", "/sbin", "/opt", "/srv", "/mnt", "/media"}
FORBIDDEN_BIND_SOURCES = FORBIDDEN_BIND_EXACT | set(FORBIDDEN_BIND_TREES)   # kept for the normalisation tests


def _expand_defaults(source: str) -> str:
    """`${VAR:-/default}` and `${VAR-/default}` read as their default (what an unset estate .env gives), so
    `${X:-/}` is the root; `${VAR}` with no default is unknown and left as it is."""
    return re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}", r"\1", source)


def _binds_forbidden_host_path(source) -> bool:
    if not isinstance(source, str):
        return False
    path = _normal_root(_expand_defaults(source))
    if path in FORBIDDEN_BIND_EXACT:
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


def check_compose(base_text: str, gb10_text: str) -> None:
    services = _services(base_text, gb10_text)
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
