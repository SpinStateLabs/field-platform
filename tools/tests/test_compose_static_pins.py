"""C-323 (reviewer C-263 F-C263-5, C-264 F-C264-1/-5): nothing pinned the image pins or the hardening.

Static, no docker: the Dockerfiles and the two compose files are read as text and parsed, and
  * every `FROM` is digest-pinned and every `pip install` in a Dockerfile is constrained
    (`-c integration/constraints.txt`, which names the approver's own dependencies too);
  * every compose `image:` is digest-pinned;
  * every healthcheck probes the port its service's own `--port` starts on;
  * every service of the merged base + GB10 compose carries no-new-privileges and `cap_drop: [ALL]`,
    and a read-only root unless it is named in READ_ONLY_EXEMPT with its reason (a new service added
    without the block fails here; the approver and the five GB10-only services did, until C-323).
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


def _tagged(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_Loader.add_multi_constructor("!", _tagged)


def _services(base_text: str, gb10_text: str) -> dict[str, dict]:
    """service -> its keys after the base file then the GB10 file (a key in the later file wins)."""
    merged: dict[str, dict] = {}
    for text in (base_text, gb10_text):
        for name, svc in (yaml.load(text, _Loader).get("services") or {}).items():
            merged.setdefault(name, {}).update(svc)
    return merged


def _logical_lines(text: str) -> list[str]:
    return re.sub(r"\\\r?\n", " ", text).splitlines()


def check_dockerfile(name: str, text: str) -> None:
    for line in _logical_lines(text):
        s = line.strip()
        if s.upper().startswith("FROM "):
            assert "@sha256:" in s, f"{name}: FROM without a digest: {s}"
        if s.upper().startswith("RUN ") and "pip install" in s:
            assert re.search(r"\s-c\s+integration/constraints\.txt\b", s), f"{name}: pip install without -c: {s}"


def check_compose(base_text: str, gb10_text: str) -> None:
    services = _services(base_text, gb10_text)
    for name, svc in sorted(services.items()):
        if "image" in svc:
            assert "@sha256:" in svc["image"], f"{name}: image without a digest: {svc['image']}"
        assert "no-new-privileges:true" in (svc.get("security_opt") or []), f"{name}: no no-new-privileges"
        assert svc.get("cap_drop") == ["ALL"], f"{name}: cap_drop is not [ALL]"
        if name not in READ_ONLY_EXEMPT:
            assert svc.get("read_only") is True, f"{name}: root file system not read-only"
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


def test_the_constraints_file_pins_the_approver_dependencies():
    names = {re.split(r"[=<>]", ln, maxsplit=1)[0].strip().lower().replace("_", "-")
             for ln in (ROOT / "integration" / "constraints.txt").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")}
    assert {"anthropic", "httpx2", "httpcore2", "jiter", "sniffio", "docstring-parser", "truststore"} <= names


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
