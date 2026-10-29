"""C-241 (Don D-21): integration/demo/docker-compose.gb10.required.yml makes the fail-open
posture variables REQUIRED (`${VAR:?message}`) so a GB10 `docker compose up` without its .env
aborts instead of starting open. The base demo compose keeps its defaults.

Static: both compose files are parsed (a loader that tolerates the compose `!override` tag), every
`${VAR:-default}` variable is derived from them and must be classified (REQUIRED, NOT_REQUIRED or
OTHER, each with a reason), and the override must list exactly the REQUIRED ones, per service.
A new variable in either file fails here until it is classified.
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

# EVERY `${VAR:-default}` variable the two compose files pass is named in exactly one of the three
# groups below; a new one in neither fails `check` (C-322: the earlier name regex missed
# FIELD_X_KEYRING and FIELD_X_ALLOW_ALL and never classified six existing variables).
#
# REQUIRED: unset or empty is a fail-open posture, and an explicit value exists (a secret, a path, 0 or 1).
REQUIRED = {
    "FIELD_SHARED_SECRET",
    "FIELD_OPERATOR_REQUIRE",
    "FIELD_LEDGER_REQUIRE_SIGNING",
    "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE",
    "FORCE_GATEWAY_ENFORCE",
    "FIELD_DOA_ROSTER",
}
# NOT_REQUIRED: posture-shaped, deliberately not required; each with its reason.
NOT_REQUIRED = {
    "FIELD_OPERATOR_REGISTRY": "blank is the only off value; pairs with FIELD_OPERATOR_REQUIRE",
    "FIELD_LEDGER_SIGN_KEY": "blank is the only off value; pairs with FIELD_LEDGER_REQUIRE_SIGNING",
    "FIELD_ATTEST_SIGNER": "blank is the only off value",
    "FIELD_ATTEST_SIGN_KEY": "blank is the only off value",
    "FIELD_LIFECYCLE_ROSTER": "blank is the only off value",
    "FORCE_GATEWAY_MOCK": "blank is the only off value; the mock switch reads exactly 1",
    "FIELD_LEDGER_CALLER_KEYRING": "blank refuses every caller claim (fail closed); pairs with FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE",
    "FIELD_KILL_ENDPOINT_ALLOWLIST": "blank is the restrictive value (the SSRF allowlist matches nothing)",
    "FIELD_LEDGER_ANCHOR_KEY": "blank is the only off value; a separate key, not read by the signing switch",
    "FORCE_GATEWAY_TOOL_CHECK": "meaningful only with FORCE_GATEWAY_ENFORCE, which is required",
    "FIELD_SENTINEL_MODE": "the default is already the safe value (enforce)",
    "FIELD_SENTINEL_JUDGE": "the default off adds no check the deterministic sentinel lacks",
}
# OTHER: not a posture switch (a tunable, a path, an identifier or a credential for an optional feature).
OTHER = {
    "ANTHROPIC_API_KEY": "credential for the optional approver profile",
    "CLAUDE_APPROVER_AGENT_MAP": "approver routing data",
    "CLAUDE_APPROVER_AGENT_MAP_FILE": "approver routing data",
    "CLAUDE_APPROVER_ENVIRONMENT_ID": "approver identifier",
    "CLAUDE_APPROVER_HALT_WAIT_SECONDS": "approver tunable",
    "CLAUDE_APPROVER_POLL_SECONDS": "approver tunable",
    "CLAUDE_APPROVER_TOOL_MAP": "approver routing data",
    "FIELD_CANARY_HEARTBEAT_EVERY": "interval tunable",
    "FIELD_CROSSWALK_EVERY": "interval tunable",
    "FIELD_JUDGE_CONFIDENCE_FLOOR": "tunable for the optional judge",
    "FIELD_JUDGE_MODEL": "model name for the optional judge",
    "FIELD_LEDGER_ARCHIVE_DIR": "path",
    "FIELD_LEDGER_OBSERVE_EVERY": "interval tunable",
    "FIELD_LEDGER_RETENTION_DAYS": "retention tunable",
    "FIELD_LIFECYCLE_EVERY": "interval tunable",
    "FIELD_MANIFEST_DIR": "path",
    "FIELD_WITNESS_EVERY": "interval tunable",
    "FIELD_WITNESS_FLY_SECRET_FILE": "path of the optional witness secret",
    "FORCE_GATEWAY_SENTINEL_TIMEOUT": "timeout tunable",
    "FORCE_TELEMETRY_RETAIN": "retention tunable",
    "FORCE_TELEMETRY_WINDOW": "window tunable",
}
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


def defaulted_vars(env: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    """variable -> services that pass it as `${VAR:-default}` under its own name (no name heuristic)."""
    found: dict[str, set[str]] = {}
    for svc, e in env.items():
        for key, value in e.items():
            m = DEFAULTED.match(value)
            if m and m.group(1) == key:
                found.setdefault(key, set()).add(svc)
    return found


def check(base_text: str, gb10_text: str, required_text: str) -> None:
    found = defaulted_vars(_merged_env(_load(base_text), _load(gb10_text)))
    groups = (REQUIRED, set(NOT_REQUIRED), set(OTHER))
    unclassified = set(found) - groups[0] - groups[1] - groups[2]
    assert not unclassified, f"variables in none of REQUIRED, NOT_REQUIRED, OTHER: {sorted(unclassified)}"
    twice = [v for i, g in enumerate(groups) for h in groups[i + 1:] for v in g & h]
    assert not twice, f"variables classified in two groups: {sorted(twice)}"
    stale = (set(NOT_REQUIRED) | set(OTHER)) - set(found)
    assert not stale, f"classified but no compose variable any more: {sorted(stale)}"
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
    "a new base variable named like a keyring, outside the old name heuristic": (
        0, lambda t: t.replace("    FIELD_DATA_DIR: /data\n",
                               "    FIELD_DATA_DIR: /data\n    FIELD_X_KEYRING: ${FIELD_X_KEYRING:-}\n", 1)),
    "a new base variable named like an allow-all, outside the old name heuristic": (
        0, lambda t: t.replace("    FIELD_DATA_DIR: /data\n",
                               "    FIELD_DATA_DIR: /data\n    FIELD_X_ALLOW_ALL: ${FIELD_X_ALLOW_ALL:-1}\n", 1)),
    "a classified variable is no longer passed by any service": (
        0, lambda t: t.replace("FIELD_CROSSWALK_EVERY", "FIELD_CROSSWALK_PERIOD")),
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


# --- the messages state the values the services really accept --------------------------------

def _message(var: str) -> str:
    text = REQUIRED_FILE.read_text(encoding="utf-8")
    m = re.search(r"\$\{" + var + r":\?([^}]+)\}", text)
    assert m, var
    return m.group(1)


def _arms(parser_module: str, fn: str, var: str, value: str, monkeypatch) -> bool:
    import importlib

    monkeypatch.setenv(var, value)
    return bool(getattr(importlib.import_module(parser_module), fn)())


# variable -> (module, function, what the parser does with an unrecognised value, wording required in the message)
PARSERS = {
    "FIELD_LEDGER_REQUIRE_SIGNING": ("sealed_ledger.api", "require_signing_from_env", False, "any other text leaves it OFF"),
    "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE": ("sealed_ledger.api", "require_caller_signature_from_env", False,
                                              "any other text leaves it OFF"),
    "FORCE_GATEWAY_ENFORCE": ("force_gateway.api", "resolve_enforce", False, "any other text leaves it OFF"),
    "FIELD_OPERATOR_REQUIRE": ("field_core.operator_auth", "_require_flag", True, "any other text also enforces"),
}


@pytest.mark.parametrize("var", sorted(PARSERS))
def test_the_message_states_what_the_service_does_with_an_unrecognised_value(var: str, monkeypatch):
    module, fn, unrecognised_arms, wording = PARSERS[var]
    assert wording in _message(var), f"{var}: the message must say: {wording}"
    assert _arms(module, fn, var, "enable", monkeypatch) is unrecognised_arms
    assert _arms(module, fn, var, "1", monkeypatch) is True
    assert _arms(module, fn, var, "0", monkeypatch) is False


def test_every_required_boolean_has_a_parser_row():
    """A required variable that is a 0/1 switch is in PARSERS; the others are values (secret, path)."""
    values = {"FIELD_SHARED_SECRET", "FIELD_DOA_ROSTER"}
    assert REQUIRED - values == set(PARSERS)


def test_the_overlay_header_says_the_guard_covers_every_compose_command():
    head = REQUIRED_FILE.read_text(encoding="utf-8").split("services:", 1)[0]
    assert "EVERY compose command" in head and "`down`" in head
