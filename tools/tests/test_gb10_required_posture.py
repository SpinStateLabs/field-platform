"""C-241 (Don D-21): integration/demo/docker-compose.gb10.required.yml makes the fail-open
posture variables REQUIRED (`${VAR:?message}`) so a GB10 `docker compose up` without its .env
aborts instead of starting open. The base demo compose keeps its defaults.

Static: both compose files are parsed (a loader that tolerates the compose `!override` tag), the
posture variables are derived from them, and the override must list exactly those, per service.
A new posture variable in either file fails here until it is classified.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DEMO = Path(__file__).resolve().parents[2] / "integration" / "demo"
BASE = DEMO / "docker-compose.yml"
GB10 = DEMO / "docker-compose.gb10.yml"
REQUIRED_FILE = DEMO / "docker-compose.gb10.required.yml"

# Variables whose unset or empty value is a fail-open posture, and which have an explicit value
# an operator can write (a secret, a path, 0 or 1): required.
REQUIRED = {
    "FIELD_SHARED_SECRET",
    "FIELD_OPERATOR_REQUIRE",
    "FIELD_LEDGER_REQUIRE_SIGNING",
    "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE",
    "FORCE_GATEWAY_ENFORCE",
    "FIELD_DOA_ROSTER",
}
# Posture-shaped variables that are deliberately NOT required: blank is their only "off" value,
# or they only matter together with a required one.
NOT_REQUIRED = {
    "FIELD_OPERATOR_REGISTRY",
    "FIELD_LEDGER_SIGN_KEY",
    "FIELD_ATTEST_SIGNER",
    "FIELD_ATTEST_SIGN_KEY",
    "FIELD_LIFECYCLE_ROSTER",
    "FORCE_GATEWAY_MOCK",
}
POSTURE_NAME = re.compile(r"REQUIRE|ENFORCE|SHARED_SECRET|ROSTER|OPERATOR_REGISTRY|SIGN|MOCK")
DEFAULTED = re.compile(r"^\$\{([A-Z0-9_]+):-")
REQUIRED_FORM = re.compile(r"^\$\{([A-Z0-9_]+):\?[^}]+\}$")


class _Loader(yaml.SafeLoader):
    pass


def _tagged(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_Loader.add_multi_constructor("!", _tagged)


def _load(text: str) -> dict:
    return yaml.load(text, _Loader)


def _merged_env(base: dict, gb10: dict) -> dict[str, dict[str, str]]:
    """service -> environment after base then GB10 (compose merges mappings key by key)."""
    env: dict[str, dict[str, str]] = {}
    for doc in (base, gb10):
        for name, svc in (doc.get("services") or {}).items():
            e = svc.get("environment") or {}
            if isinstance(e, list):
                e = dict(x.split("=", 1) for x in e if "=" in x)
            env.setdefault(name, {}).update({k: str(v) for k, v in e.items()})
    return env


def posture_vars(env: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    """variable -> services that pass it as `${VAR:-default}` and whose name looks like posture."""
    found: dict[str, set[str]] = {}
    for svc, e in env.items():
        for key, value in e.items():
            m = DEFAULTED.match(value)
            if m and m.group(1) == key and POSTURE_NAME.search(key):
                found.setdefault(key, set()).add(svc)
    return found


def check(base_text: str, gb10_text: str, required_text: str) -> None:
    found = posture_vars(_merged_env(_load(base_text), _load(gb10_text)))
    unclassified = set(found) - REQUIRED - NOT_REQUIRED
    assert not unclassified, f"posture variables in neither REQUIRED nor NOT_REQUIRED: {sorted(unclassified)}"
    override = (_load(required_text).get("services") or {})
    expected = {(svc, var) for var, svcs in found.items() if var in REQUIRED for svc in svcs}
    listed: set[tuple[str, str]] = set()
    for svc, body in override.items():
        for key, value in (body.get("environment") or {}).items():
            m = REQUIRED_FORM.match(str(value))
            assert m and m.group(1) == key, f"{svc}.{key} is not `${{{key}:?message}}`"
            listed.add((svc, key))
    assert expected - listed == set(), f"required but not listed: {sorted(expected - listed)}"
    assert listed - expected == set(), f"listed but not a posture variable of that service: {sorted(listed - expected)}"
    missing_vars = REQUIRED - set(found)
    assert not missing_vars, f"REQUIRED names no compose variable any more: {sorted(missing_vars)}"


def _texts() -> tuple[str, str, str]:
    return (BASE.read_text(encoding="utf-8"), GB10.read_text(encoding="utf-8"),
            REQUIRED_FILE.read_text(encoding="utf-8"))


def test_the_required_file_lists_exactly_the_posture_variables_of_the_two_compose_files():
    check(*_texts())


def test_the_base_demo_compose_keeps_its_defaults_and_requires_nothing():
    base = BASE.read_text(encoding="utf-8")
    assert ":?" not in base, "the base demo compose must keep its demo defaults"
    assert "${FIELD_SHARED_SECRET:-}" in base


def test_the_required_file_has_no_literal_values():
    for value in (REQUIRED_FILE.read_text(encoding="utf-8")).splitlines():
        if value.lstrip().startswith("#") or ":" not in value or value.rstrip().endswith(":"):
            continue
        key, _, rest = value.strip().partition(": ")
        if key in ("services", "environment") or rest == "":
            continue
        assert rest.startswith("${") and ":?" in rest, f"literal or non-required value: {value.strip()}"


# --- mutants: each must turn `check` RED ------------------------------------------------------

MUTANTS = {
    "a required entry becomes a default": (
        2, lambda t: t.replace("${FIELD_SHARED_SECRET:?", "${FIELD_SHARED_SECRET:-", 1)),
    "a service entry is dropped": (
        2, lambda t: t.replace("  registry:\n    environment:", "  registry:\n    environment: {}\n    x-dropped:", 1)),
    "the enforce variable is not listed for the gateway": (
        2, lambda t: re.sub(r"\n      FORCE_GATEWAY_ENFORCE: [^\n]+", "", t, count=1)),
    "a new posture variable appears in the base file": (
        0, lambda t: t.replace("    FIELD_DATA_DIR: /data\n",
                               "    FIELD_DATA_DIR: /data\n    FIELD_NEW_ENFORCE: ${FIELD_NEW_ENFORCE:-0}\n", 1)),
    "the override requires a variable no service passes": (
        2, lambda t: t.replace("services:\n", "services:\n  nosuch:\n    environment:\n"
                               "      FIELD_LEDGER_SIGN_KEY: ${FIELD_LEDGER_SIGN_KEY:?x}\n", 1)),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_turns_the_check_red(name: str):
    which, mutate = MUTANTS[name]
    texts = list(_texts())
    mutated = mutate(texts[which])
    assert mutated != texts[which], f"mutant {name!r} changed nothing"
    texts[which] = mutated
    with pytest.raises(AssertionError):
        check(*texts)
