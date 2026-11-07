"""G22 compose pass-through: ``FIELD_INTERNAL_SECRET_SHA256`` reaches the eight operator-block services, as a blank-by-default
interpolation of the estate .env, and nothing else holds an internal secret.

Why: the Stage 2 entry check (``phase_g_check --stage 2``) reads ``internal_secret_sha256_present`` from the kill-switch
and registry ``/health``; before this pass-through no compose file gave any service the variable, so it read 0 of 2 even
with the hash in the estate .env. The value form ``FIELD_INTERNAL_SECRET`` is the rotator's file mount only, never an
env var on a service. No secret or hash value is written in any file here."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "integration" / "demo"
BASE = DEMO / "docker-compose.yml"
EIGHT = ("registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle")
NAME = "FIELD_INTERNAL_SECRET_SHA256"
PASS = "${FIELD_INTERNAL_SECRET_SHA256:-}"


class _Loader(yaml.SafeLoader):
    """Compose tags (``!override``, ``!reset``) are read as the plain value they wrap."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: (
    loader.construct_sequence(node, deep=True) if isinstance(node, yaml.SequenceNode)
    else loader.construct_mapping(node, deep=True) if isinstance(node, yaml.MappingNode)
    else loader.construct_scalar(node)))


def services(path: Path = BASE) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)["services"]


def env_of(svc: dict) -> dict:
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, None) for item in env)
    return env


def holders(svcs: dict) -> list[str]:
    return sorted(n for n, s in svcs.items() if NAME in env_of(s))


@pytest.mark.parametrize("name", EIGHT)
def test_each_operator_block_service_passes_the_hash_blank_by_default(name):
    assert env_of(services()[name]).get(NAME) == PASS


def test_exactly_the_eight_services_hold_it_and_no_other_service_does():
    assert holders(services()) == sorted(EIGHT)


def test_the_value_form_is_never_an_env_var_on_any_service_and_no_compose_file_holds_a_value():
    for path in sorted(DEMO.glob("docker-compose*.yml")):
        for name, svc in services(path).items():
            assert "FIELD_INTERNAL_SECRET" not in env_of(svc), (path.name, name)
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"FIELD_INTERNAL_SECRET_SHA256\s*[:=]\s*(\S+)", text):
            assert m.group(1) in {PASS, "${FIELD_INTERNAL_SECRET_SHA256:-}"} or m.group(1).startswith("#"), (path.name, m.group(0))
        for line in text.splitlines():                                    # a hash literal has no place on such a line
            assert "INTERNAL_SECRET" not in line or not re.search(r"\b[0-9a-f]{64}\b", line), (path.name, line[:40])


def test_the_overlays_do_not_override_the_pass_through():
    for path in sorted(DEMO.glob("docker-compose.gb10*.yml")):
        for name, svc in services(path).items():
            if NAME in env_of(svc):
                assert env_of(svc)[NAME] == PASS, (path.name, name)
