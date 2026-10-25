"""Phase G plumbing: the deployment descriptors pass FIELD_OPERATOR_REGISTRY and
FIELD_OPERATOR_REQUIRE to exactly the services that apply operator auth, with
EMPTY defaults, and mount the operators file read-only. Reads the YAML only
(docker is not needed); whether Docker honours the mount is declared in the
runbook, not proven here."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "integration" / "demo"
FLAGS = ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE")
MOUNT = "${FIELD_OPERATORS_FILE:-./operators.empty.json}:/run/field/operators.json:ro"

#: service source dir -> compose service name, for every service that imports operator_auth.
EXPECTED = {
    "agent-registry": "registry",
    "sealed-ledger": "ledger",
    "delegation-authority": "delegation",
    "kill-switch": "killswitch",
    "spend-governor": "governor",
    "federation-broker": "fedbroker",
    "ops-console": "console",
    "lifecycle-manager": "lifecycle",
}


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor(
    "!override", lambda l, n: l.construct_sequence(n)
    if isinstance(n, yaml.SequenceNode) else l.construct_scalar(n))


def _compose(name: str) -> dict:
    return yaml.load((DEMO / name).read_text(encoding="utf-8"), Loader=_Loader)


def _env(svc: dict) -> dict:
    e = svc.get("environment") or {}
    if isinstance(e, list):
        e = dict(x.split("=", 1) for x in e)
    return {k: ("" if v is None else str(v)) for k, v in e.items()}


@pytest.fixture(scope="module", params=["docker-compose.yml", "docker-compose.gb10.yml"])
def compose(request):
    return request.param, _compose(request.param)


def test_the_expected_set_is_every_service_that_imports_operator_auth():
    found = {p.parts[-4] for p in (REPO / "services").glob("*/src/*/*.py")
             if re.search(r"^\s*(from field_core import operator_auth|import field_core\.operator_auth|"
                          r"from field_core\.operator_auth import)", p.read_text(encoding="utf-8"), re.M)}
    assert found == set(EXPECTED), "a service started (or stopped) applying operator auth: update EXPECTED and the compose files"


def test_base_file_passes_both_flags_with_empty_defaults_to_exactly_the_expected_services():
    services = _compose("docker-compose.yml")["services"]
    for name, svc in services.items():
        env = _env(svc)
        if name in EXPECTED.values():
            for f in FLAGS:
                assert env.get(f) == "${%s:-}" % f, (name, f, env.get(f))
        else:
            assert not any(f in env for f in FLAGS), name


def test_the_gb10_file_never_sets_a_flag_to_anything_but_the_blank_default(compose):
    fname, doc = compose
    for name, svc in doc["services"].items():
        env = _env(svc)
        for f in FLAGS:
            if f in env:
                assert env[f] == "${%s:-}" % f, (fname, name, f, env[f])


def test_no_service_in_either_file_has_a_non_blank_operator_literal(compose):
    fname, doc = compose
    text = (DEMO / fname).read_text(encoding="utf-8")
    for f in FLAGS:
        for m in re.finditer(r"^\s*%s\s*[:=]\s*(.+)$" % f, text, re.M):
            assert m.group(1).strip().strip("\"'") == "${%s:-}" % f, (fname, m.group(0))


def test_the_operators_file_is_mounted_read_only_into_exactly_the_expected_services(compose):
    fname, doc = compose
    for name, svc in doc["services"].items():
        vols = [v for v in (svc.get("volumes") or []) if isinstance(v, str)]
        ops = [v for v in vols if "operators" in v]
        if name in EXPECTED.values():
            assert ops == [MOUNT], (fname, name, ops)
        else:
            assert ops == [], (fname, name, ops)


def test_the_default_bind_source_is_a_committed_empty_operator_list():
    p = DEMO / "operators.empty.json"
    assert p.is_file()     # a missing bind source would be created as a directory
    assert json.loads(p.read_text(encoding="utf-8")) == {"operators": []}
    from field_core import operator_auth as oa
    assert oa.load_registry(str(p)) == []


def test_fly_toml_env_does_not_set_the_flags_and_the_entrypoint_only_defaults_them_blank():
    toml = (REPO / "integration" / "fly" / "fly.toml").read_text(encoding="utf-8")
    for f in FLAGS + ("FIELD_OPERATORS_FILE",):
        assert not re.search(r"^\s*%s\s*=" % f, toml, re.M), f
    entry = (REPO / "integration" / "fly" / "entrypoint.sh").read_text(encoding="utf-8")
    for f in FLAGS:
        assert re.findall(r"^(?:export\s+)?%s=.*$" % f, entry, re.M) == ['export %s="${%s:-}"' % (f, f)]


# --- the EFFECTIVE config: base + gb10 override merged the way Compose merges ---

def _target(vol: str) -> str:
    parts = re.sub(r"\$\{[^}]*\}", "X", vol).split(":")   # ${VAR:-default} holds a colon
    # host-or-volume:target[:mode]; the target is the 2nd field
    return parts[1] if len(parts) > 1 else parts[0]


def _merged() -> dict:
    """environment merges by key, volumes by target path (the override wins on
    a clash); every other key is not needed here. Both files list ``name`` so a
    service present only in the override (witness, canary-agent) is kept."""
    base, over = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")
    out = {}
    for name in set(base["services"]) | set(over["services"]):
        env, vols = {}, {}
        for doc in (base, over):
            svc = doc["services"].get(name) or {}
            env.update(_env(svc))
            for v in svc.get("volumes") or []:
                if isinstance(v, str):
                    vols[_target(v)] = v
        out[name] = {"environment": env, "volumes": vols}
    return out


def test_merged_config_carries_flags_and_mount_on_exactly_the_expected_services():
    m = _merged()
    for name, svc in m.items():
        has_flags = [f for f in FLAGS if f in svc["environment"]]
        mount = svc["volumes"].get("/run/field/operators.json")
        if name in EXPECTED.values():
            assert has_flags == list(FLAGS) and all(
                svc["environment"][f] == "${%s:-}" % f for f in FLAGS), name
            assert mount == MOUNT, name
        else:
            assert has_flags == [] and mount is None, name


def test_merged_config_keeps_the_shared_env_and_the_data_volume_on_the_operator_services():
    base = _compose("docker-compose.yml")
    shared = _env(base["x-service"])
    assert "FIELD_DATA_DIR" in shared and "FIELD_LEDGER_URL" in shared
    m = _merged()
    for name in EXPECTED.values():
        # dropping `*env` (keeping only the operator anchor) would lose these
        for k, v in shared.items():
            assert m[name]["environment"].get(k) == v, (name, k)
        assert m[name]["volumes"].get("/data") == "field-data:/data", name


def test_base_file_alone_keeps_the_data_volume_and_shared_env_on_the_operator_services():
    base = _compose("docker-compose.yml")
    shared = _env(base["x-service"])
    for name in EXPECTED.values():
        svc = base["services"][name]
        assert "field-data:/data" in svc["volumes"], name
        for k, v in shared.items():
            assert _env(svc).get(k) == v, (name, k)
