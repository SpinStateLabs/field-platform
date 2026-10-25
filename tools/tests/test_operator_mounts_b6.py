"""Phase G Stage 0, B-6 and C-1 (compose part).

B-6: the operators registry is a read-only DIRECTORY mount at
/run/field/operators/ in exactly the eight operator-auth services, from
FIELD_OPERATORS_DIR (default: the committed placeholder directory
integration/demo/operators/ holding one zero-row operators.json). A single-file
bind pins the host inode, so a replaced file is never seen by a running
container; a directory bind is, which makes "write a temp file in that
directory, then mv" the one edit method.

C-1 (compose part): the four daemon identities (killswitch, registry,
delegation, lifecycle) each get a read-only key FILE mount at
/run/field/operator.key from their own host variable (default: the committed
empty placeholder integration/demo/operator-key.empty), plus FIELD_OPERATOR and
FIELD_OPERATOR_KEY_FILE, and nobody else gets any of it.

Reads the YAML and the docs only (docker is not needed). Whether Docker follows
a rename inside a directory bind is declared in the runbook, not proven here.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "integration" / "demo"
RUNBOOK = REPO / "docs" / "runbooks" / "v1.2-deploy-rollback.md"
ENV_EXAMPLE = REPO / ".env.example"
FILES = ("docker-compose.yml", "docker-compose.gb10.yml")

OPS_TARGET = "/run/field/operators"
OPS_MOUNT = "${FIELD_OPERATORS_DIR:-./operators}:/run/field/operators:ro"
OPS_PLACEHOLDER_DIR = DEMO / "operators"
OPS_REGISTRY_PATH = "/run/field/operators/operators.json"

KEY_TARGET = "/run/field/operator.key"
KEY_PLACEHOLDER = DEMO / "operator-key.empty"

#: the eight services that import operator_auth (pinned against the source tree
#: by tools/tests/test_operator_plumbing.py::EXPECTED).
OPERATOR_AUTH_SERVICES = frozenset(
    {"registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle"})

#: C-1: compose service -> (operator id, host variable naming ITS key file). Design 2.2.1.
DAEMONS = {
    "killswitch": ("svc-killswitch", "FIELD_OPERATOR_KEY_KILLSWITCH_FILE"),
    "registry": ("svc-registry", "FIELD_OPERATOR_KEY_REGISTRY_FILE"),
    "delegation": ("svc-delegation", "FIELD_OPERATOR_KEY_DELEGATION_FILE"),
    "lifecycle": ("svc-lifecycle", "FIELD_OPERATOR_KEY_LIFECYCLE_FILE"),
}
IDENTITY_ENV = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE", "FIELD_OPERATOR_KEY")


def _key_mount(var: str) -> str:
    return "${%s:-./operator-key.empty}:/run/field/operator.key:ro" % var


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor(
    "!override", lambda l, n: l.construct_sequence(n)
    if isinstance(n, yaml.SequenceNode) else l.construct_scalar(n))


def _compose(name: str) -> dict:
    return yaml.load((DEMO / name).read_text(encoding="utf-8"), Loader=_Loader)


def _code_lines(name: str) -> list[str]:
    """The compose file without comment lines (comments may name the old habit)."""
    return [ln for ln in (DEMO / name).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def _env(svc: dict) -> dict:
    e = svc.get("environment") or {}
    if isinstance(e, list):
        e = dict(x.split("=", 1) for x in e)
    return {k: ("" if v is None else str(v)) for k, v in e.items()}


def _vols(svc: dict) -> list[str]:
    return [v for v in (svc.get("volumes") or []) if isinstance(v, str)]


def _split(vol: str) -> tuple[str, str, str]:
    """(source, target, mode) of a short-syntax volume; ${VAR:-default} holds a colon."""
    m = re.fullmatch(r"(\$\{[^}]*\}[^:]*|[^:]+):([^:]+)(?::([^:]+))?", vol)
    assert m, vol
    return m.group(1), m.group(2), m.group(3) or "rw"


def _merged() -> dict:
    """Base + gb10 override merged the way Compose merges them: environment by
    key, volumes by target (the override wins on a clash)."""
    base, over = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")
    out = {}
    for name in set(base["services"]) | set(over["services"]):
        env, vols = {}, {}
        for doc in (base, over):
            svc = doc["services"].get(name) or {}
            env.update(_env(svc))
            for v in _vols(svc):
                vols[_split(v)[1]] = v
        out[name] = {"environment": env, "volumes": vols}
    return out


@pytest.fixture(scope="module", params=FILES)
def compose(request):
    return request.param, _compose(request.param)


# --- B-6: the operators registry is a directory mount -----------------------------------------


def test_the_default_operators_source_is_a_committed_directory_holding_a_zero_row_registry():
    assert OPS_PLACEHOLDER_DIR.is_dir()          # a missing bind source would be created empty
    assert sorted(p.name for p in OPS_PLACEHOLDER_DIR.iterdir()) == ["operators.json"]
    f = OPS_PLACEHOLDER_DIR / "operators.json"
    assert json.loads(f.read_text(encoding="utf-8")) == {"operators": []}
    from field_core import operator_auth as oa
    assert oa.load_registry(str(f)) == []
    # the path the flag is pointed at is that file, inside the mount target
    assert OPS_REGISTRY_PATH == "%s/%s" % (OPS_TARGET, f.name)


def test_the_single_file_operators_bind_is_gone_from_both_files_and_the_repo(compose):
    fname, doc = compose
    code = "\n".join(_code_lines(fname))
    for old in ("operators.empty.json", "/run/field/operators.json", "FIELD_OPERATORS_FILE"):
        assert old not in code, (fname, old)
    for name, svc in doc["services"].items():
        for v in _vols(svc):
            assert _split(v)[1] != "/run/field/operators.json", (fname, name, v)
    # never both habits on one estate: no stale single-file placeholder to point a bind at
    assert not (DEMO / "operators.empty.json").exists()


def test_the_operators_directory_is_mounted_read_only_into_exactly_the_eight(compose):
    fname, doc = compose
    for name, svc in doc["services"].items():
        ops = [v for v in _vols(svc) if _split(v)[1].startswith(OPS_TARGET)]
        if name in OPERATOR_AUTH_SERVICES:
            assert ops == [OPS_MOUNT], (fname, name, ops)
            assert _split(ops[0])[2] == "ro", (fname, name)
        else:
            assert ops == [], (fname, name, ops)


def test_the_merged_config_mounts_the_operators_directory_read_only_on_exactly_the_eight():
    m = _merged()
    assert OPERATOR_AUTH_SERVICES <= set(m)
    for name, svc in m.items():
        ops = {t: v for t, v in svc["volumes"].items() if t.startswith(OPS_TARGET)}
        if name in OPERATOR_AUTH_SERVICES:
            assert ops == {OPS_TARGET: OPS_MOUNT}, (name, ops)
        else:
            assert ops == {}, (name, ops)


# --- C-1 (compose part): daemon key files and identities --------------------------------------


def test_the_default_key_source_is_a_committed_empty_file():
    assert KEY_PLACEHOLDER.is_file()             # a missing FILE source becomes a directory
    assert KEY_PLACEHOLDER.stat().st_size == 0


def test_each_daemon_gets_its_own_read_only_key_file_mount_and_nobody_else_gets_one(compose):
    fname, doc = compose
    for name, svc in doc["services"].items():
        keys = [v for v in _vols(svc) if _split(v)[1] == KEY_TARGET or "FIELD_OPERATOR_KEY" in v]
        if name in DAEMONS:
            assert keys == [_key_mount(DAEMONS[name][1])], (fname, name, keys)
            assert _split(keys[0])[2] == "ro", (fname, name)
        else:
            assert keys == [], (fname, name, keys)


def test_every_daemon_reads_a_different_host_variable_and_each_appears_once_per_file(compose):
    fname, _ = compose
    variables = [var for _, var in DAEMONS.values()]
    assert len(set(variables)) == len(variables) == 4
    code = "\n".join(_code_lines(fname))
    for var in variables:
        assert len(re.findall(r"\$\{%s:-" % var, code)) == 1, (fname, var)
    # no other FIELD_OPERATOR_KEY_*_FILE host variable exists in the descriptor
    assert set(re.findall(r"\$\{(FIELD_OPERATOR_KEY_[A-Z]+_FILE):-", code)) == set(variables), fname


def test_the_merged_config_gives_the_identity_and_key_mount_to_exactly_the_four_daemons():
    m = _merged()
    assert set(DAEMONS) <= set(m)
    for name, svc in m.items():
        env = svc["environment"]
        if name in DAEMONS:
            op_id, var = DAEMONS[name]
            assert env.get("FIELD_OPERATOR") == op_id, name
            assert env.get("FIELD_OPERATOR_KEY_FILE") == KEY_TARGET, name
            assert svc["volumes"].get(KEY_TARGET) == _key_mount(var), name
        else:
            # the console forwards the human and must never present a service identity;
            # the sentinel, gateway, ledger, governor, fedbroker, witness and canary hold none
            assert not any(k in env for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE")), name
            assert KEY_TARGET not in svc["volumes"], name
        assert "FIELD_OPERATOR_KEY" not in env, name   # the raw key is never a descriptor value


def test_no_descriptor_passes_a_raw_key_and_the_identity_values_are_fixed_literals(compose):
    fname, _ = compose
    code = "\n".join(_code_lines(fname))
    assert not re.search(r"^\s*-?\s*FIELD_OPERATOR_KEY\s*[:=]", code, re.M), fname
    key_files = re.findall(r"^\s*FIELD_OPERATOR_KEY_FILE\s*:\s*(.+?)\s*$", code, re.M)
    ids = re.findall(r"^\s*FIELD_OPERATOR\s*:\s*(.+?)\s*$", code, re.M)
    if fname == "docker-compose.yml":
        assert key_files == [KEY_TARGET] * 4, key_files
        assert sorted(ids) == sorted(op_id for op_id, _ in DAEMONS.values()), ids
    else:
        # the override merges environment by key (test_deploy_docs pins its lifecycle env exactly)
        assert key_files == [] and ids == [], (key_files, ids)


def _default(value: str) -> str:
    """What Compose interpolates with no host variable set: ${X:-d} -> d, ${X} -> ''."""
    return re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::?-([^}]*))?\}", lambda mo: mo.group(1) or "", value)


def test_with_the_defaults_mounted_the_daemons_present_no_identity(monkeypatch):
    """Inert until the host files exist: each daemon's operator env as Compose
    renders it with no host variable set, with the in-container key path mapped
    to the file the default bind mounts there. operator_headers() sends the pair
    only when both id and key are non-empty."""
    from field_core import authn
    from field_core import operator_auth as oa

    m = _merged()
    for name in DAEMONS:
        env, vols = m[name]["environment"], m[name]["volumes"]
        for k in list(os.environ):
            if k.startswith("FIELD_OPERATOR") or k == "FIELD_SHARED_SECRET":
                monkeypatch.delenv(k)
        for k, v in env.items():
            if k.startswith("FIELD_OPERATOR") or k == "FIELD_SHARED_SECRET":
                monkeypatch.setenv(k, _default(v))
        assert os.environ["FIELD_OPERATOR_KEY_FILE"] == KEY_TARGET, name
        src = DEMO / _default(_split(vols[KEY_TARGET])[0])
        assert src.resolve() == KEY_PLACEHOLDER.resolve(), name
        monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(src))
        assert oa.mode() == oa.OFF, name
        assert oa.operator_headers() == {}, name
        assert authn.auth_headers() == {}, name


# --- docs: .env.example and runbook section 7 say what the descriptors do -----------------------


def _env_example_phase_g() -> str:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return text[text.index("# Phase G authenticated operators"):]


def test_env_example_names_the_directory_the_registry_path_and_the_four_key_files_commented_out():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    g = _env_example_phase_g()
    assert re.search(r"^# FIELD_OPERATORS_DIR=/\S+", g, re.M)
    assert re.search(r"^# FIELD_OPERATOR_REGISTRY=%s\s" % re.escape(OPS_REGISTRY_PATH), g, re.M)
    for _, var in DAEMONS.values():
        assert re.search(r"^# %s=/\S+\.key\s" % var, g, re.M), var
    # nothing armed by the example, and the withdrawn single-file names are gone
    assert not re.search(r"^\s*FIELD_OPERATOR", text, re.M)
    for old in ("FIELD_OPERATORS_FILE", "/run/field/operators.json", "operators.empty.json"):
        assert old not in text, old


def _section7() -> str:
    text = RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("## 7. Phase G")
    nxt = text.find("\n## ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def test_runbook_section_7_documents_the_directory_mount_and_mv_as_the_only_edit_method():
    s7 = _section7()
    assert "`FIELD_OPERATORS_DIR`" in s7 and "`%s/`" % OPS_TARGET in s7
    assert OPS_REGISTRY_PATH in s7 and "integration/demo/operators/" in s7
    assert "ONLY edit method" in s7 and "mv -f" in s7
    for _, var in DAEMONS.values():
        assert "`%s`" % var in s7, var
    assert "`integration/demo/operator-key.empty`" in s7 and "`%s`" % KEY_TARGET in s7
    # the withdrawn single-file habit is not offered anywhere in the section
    for old in ("cat new.json >", "/run/field/operators.json", "FIELD_OPERATORS_FILE", "operators.empty.json",
                "Edit IN PLACE"):
        assert old not in s7, old
    assert not re.search(r"\bcat\s+[^\n`]*>\s*\S*operators\.json", s7)
