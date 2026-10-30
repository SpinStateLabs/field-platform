"""Phase G Stage 0, B-6 and C-1 (compose part).

B-6: the operators registry is a read-only DIRECTORY mount at
/run/field/operators/ in exactly the eight operator-auth services, from
FIELD_OPERATORS_DIR (default: the committed placeholder directory
integration/demo/operators/ holding one zero-row operators.json). A single-file
bind pins the host inode, so a replaced file is never seen by a running
container; a directory bind is, which makes "write a temp file in that
directory, then mv" the one edit method.

C-1 (compose part): the four daemon identities (killswitch, registry,
delegation, lifecycle) each get a read-only key DIRECTORY mount at
/run/field/keys/ from their own host variable FIELD_OPERATOR_KEY_DIR_<SVC>
(default: the committed placeholder directory
integration/demo/operator-keys/svc-<name>/ holding one EMPTY svc-<name>.key),
plus FIELD_OPERATOR=svc-<name> and
FIELD_OPERATOR_KEY_FILE=/run/field/keys/svc-<name>.key, and nobody else gets
any of it (PG0-COMPOSE-R1-01). A directory for the B-6 reason: a key rotated by
`mv` inside the directory is seen by the running daemon, where a single-file
bind would keep presenting the old (revoked) key, a kill-switch that silently
cannot kill. One directory PER daemon so no daemon can read another's key; the
name-bearing file name means a daemon handed another daemon's directory finds
no key file (no identity) rather than the other daemon's identity.

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

KEY_TARGET = "/run/field/keys"
KEY_PLACEHOLDER_ROOT = DEMO / "operator-keys"
#: the withdrawn single-file key bind (PG0-COMPOSE-R1-01): must not come back
OLD_KEY_TARGET = "/run/field/operator.key"
OLD_KEY_PLACEHOLDER = DEMO / "operator-key.empty"

#: the eight services that import operator_auth (pinned against the source tree
#: by tools/tests/test_operator_plumbing.py::EXPECTED).
OPERATOR_AUTH_SERVICES = frozenset(
    {"registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle"})

#: C-1: compose service -> (operator id, host variable naming ITS key directory). Design 2.2.1, 9.5.
DAEMONS = {
    "killswitch": ("svc-killswitch", "FIELD_OPERATOR_KEY_DIR_KILLSWITCH"),
    "registry": ("svc-registry", "FIELD_OPERATOR_KEY_DIR_REGISTRY"),
    "delegation": ("svc-delegation", "FIELD_OPERATOR_KEY_DIR_DELEGATION"),
    "lifecycle": ("svc-lifecycle", "FIELD_OPERATOR_KEY_DIR_LIFECYCLE"),
}
IDENTITY_ENV = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE", "FIELD_OPERATOR_KEY")


def _key_mount(op_id: str, var: str) -> str:
    return "${%s:-./operator-keys/%s}:%s:ro" % (var, op_id, KEY_TARGET)


def _key_file(op_id: str) -> str:
    """The in-container key path: inside the mounted directory, named after the identity."""
    return "%s/%s.key" % (KEY_TARGET, op_id)


def _key_placeholder(op_id: str) -> Path:
    return KEY_PLACEHOLDER_ROOT / op_id / ("%s.key" % op_id)


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


def _is_key_mount(vol: str) -> bool:
    t = _split(vol)[1]
    return (t == KEY_TARGET or t.startswith(KEY_TARGET + "/") or t == OLD_KEY_TARGET
            or "FIELD_OPERATOR_KEY" in vol or "operator-key" in vol)


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


# --- C-1 (compose part): daemon key directories and identities -------------------------------


def test_the_default_key_sources_are_committed_per_daemon_directories_each_holding_one_empty_key():
    assert KEY_PLACEHOLDER_ROOT.is_dir()
    assert sorted(p.name for p in KEY_PLACEHOLDER_ROOT.iterdir()) == sorted(op for op, _ in DAEMONS.values())
    for op_id, _ in DAEMONS.values():
        d = KEY_PLACEHOLDER_ROOT / op_id
        assert d.is_dir(), op_id                     # a missing bind source would be created empty
        # exactly one file, named after THIS identity: a daemon handed another daemon's
        # directory finds no file at its own key path, so it presents no identity
        assert sorted(p.name for p in d.iterdir()) == ["%s.key" % op_id], op_id
        f = _key_placeholder(op_id)
        assert f.is_file() and f.stat().st_size == 0, op_id   # empty key => no identity
    # never both habits: the withdrawn single-file placeholder is gone
    assert not OLD_KEY_PLACEHOLDER.exists()


def test_the_single_file_key_bind_is_gone_from_both_files(compose):
    fname, doc = compose
    code = "\n".join(_code_lines(fname))
    for old in (OLD_KEY_TARGET, "operator-key.empty"):
        assert old not in code, (fname, old)
    assert not re.search(r"FIELD_OPERATOR_KEY_[A-Z_]*_FILE", code), fname
    for name, svc in doc["services"].items():
        for v in _vols(svc):
            assert _split(v)[1] != OLD_KEY_TARGET, (fname, name, v)


def test_each_daemon_gets_its_own_read_only_key_directory_mount_and_nobody_else_gets_one(compose):
    fname, doc = compose
    for name, svc in doc["services"].items():
        keys = [v for v in _vols(svc) if _is_key_mount(v)]
        if name in DAEMONS:
            assert keys == [_key_mount(*DAEMONS[name])], (fname, name, keys)
            assert _split(keys[0])[2] == "ro", (fname, name)
        else:
            assert keys == [], (fname, name, keys)


def test_every_daemon_reads_a_different_host_variable_and_directory_and_each_appears_once_per_file(compose):
    fname, _ = compose
    variables = [var for _, var in DAEMONS.values()]
    assert len(set(variables)) == len(variables) == 4
    defaults = [_split(_key_mount(op, var))[0] for op, var in DAEMONS.values()]
    assert len(set(defaults)) == 4                   # no shared keys directory
    code = "\n".join(_code_lines(fname))
    for var in variables:
        assert len(re.findall(r"\$\{%s:-" % var, code)) == 1, (fname, var)
    # no other FIELD_OPERATOR_KEY_DIR_* host variable exists in the descriptor
    assert set(re.findall(r"\$\{(FIELD_OPERATOR_KEY_DIR_[A-Z]+):-", code)) == set(variables), fname


def test_the_merged_config_gives_the_identity_and_key_mount_to_exactly_the_four_daemons():
    m = _merged()
    assert set(DAEMONS) <= set(m)
    for name, svc in m.items():
        env = svc["environment"]
        if name in DAEMONS:
            op_id, var = DAEMONS[name]
            assert env.get("FIELD_OPERATOR") == op_id, name
            assert env.get("FIELD_OPERATOR_KEY_FILE") == _key_file(op_id), name
            # the key file name carries the identity it belongs to
            assert env["FIELD_OPERATOR_KEY_FILE"] == "%s/%s.key" % (KEY_TARGET, env["FIELD_OPERATOR"]), name
            assert svc["volumes"].get(KEY_TARGET) == _key_mount(op_id, var), name
        else:
            # the console forwards the human and must never present a service identity;
            # the sentinel, gateway, ledger, governor, fedbroker, witness and canary hold none
            assert not any(k in env for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE")), name
            assert KEY_TARGET not in svc["volumes"], name
        assert OLD_KEY_TARGET not in svc["volumes"], name
        assert "FIELD_OPERATOR_KEY" not in env, name   # the raw key is never a descriptor value


def test_no_descriptor_passes_a_raw_key_and_the_identity_values_are_fixed_literals(compose):
    fname, _ = compose
    code = "\n".join(_code_lines(fname))
    assert not re.search(r"^\s*-?\s*FIELD_OPERATOR_KEY\s*[:=]", code, re.M), fname
    key_files = re.findall(r"^\s*FIELD_OPERATOR_KEY_FILE\s*:\s*(.+?)\s*$", code, re.M)
    ids = re.findall(r"^\s*FIELD_OPERATOR\s*:\s*(.+?)\s*$", code, re.M)
    if fname == "docker-compose.yml":
        assert sorted(key_files) == sorted(_key_file(op_id) for op_id, _ in DAEMONS.values()), key_files
        assert sorted(ids) == sorted(op_id for op_id, _ in DAEMONS.values()), ids
    else:
        # the override merges environment by key (test_deploy_docs pins its lifecycle env exactly)
        assert key_files == [] and ids == [], (key_files, ids)


def _default(value: str) -> str:
    """What Compose interpolates with no host variable set: ${X:-d} -> d, ${X} -> ''."""
    return re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::?-([^}]*))?\}", lambda mo: mo.group(1) or "", value)


def test_with_the_defaults_mounted_the_daemons_present_no_identity(monkeypatch):
    """Inert until the host key files exist: each daemon's operator env as Compose
    renders it with no host variable set, with the in-container key path mapped
    to the file at the same place inside the directory the default bind mounts.
    operator_headers() sends the pair only when both id and key are non-empty."""
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
        op_id = DAEMONS[name][0]
        key_file = os.environ["FIELD_OPERATOR_KEY_FILE"]
        assert key_file == _key_file(op_id), name
        src_dir = DEMO / _default(_split(vols[KEY_TARGET])[0])
        src = src_dir / key_file[len(KEY_TARGET) + 1:]
        assert src.resolve() == _key_placeholder(op_id).resolve(), name
        assert src.is_file() and src.stat().st_size == 0, name
        monkeypatch.setenv("FIELD_OPERATOR_KEY_FILE", str(src))
        assert oa.mode() == oa.OFF, name
        assert oa.operator_headers() == {}, name
        assert authn.auth_headers() == {}, name


# --- docs: .env.example and runbook section 7 say what the descriptors do -----------------------


def _env_example_phase_g() -> str:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return text[text.index("# Phase G authenticated operators"):]


def test_env_example_names_the_directory_the_registry_path_and_the_four_key_directories_commented_out():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    g = _env_example_phase_g()
    assert re.search(r"^# FIELD_OPERATORS_DIR=/\S+", g, re.M)
    assert re.search(r"^# FIELD_OPERATOR_REGISTRY=%s\s" % re.escape(OPS_REGISTRY_PATH), g, re.M)
    for op_id, var in DAEMONS.values():
        # a per-daemon host DIRECTORY named after the identity, not a key file path
        assert re.search(r"^# %s=/\S+/%s\s" % (var, re.escape(op_id)), g, re.M), var
    # nothing armed by the example, and the withdrawn single-file names are gone
    assert not re.search(r"^\s*FIELD_OPERATOR", text, re.M)
    for old in ("FIELD_OPERATORS_FILE", "/run/field/operators.json", "operators.empty.json",
                OLD_KEY_TARGET, "operator-key.empty"):
        assert old not in text, old
    assert not re.search(r"FIELD_OPERATOR_KEY_[A-Z_]*_FILE", text)


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
    # per-daemon key directories: repo placeholder, in-container path, GB10 host layout
    assert "`integration/demo/operator-keys/svc-<name>/`" in s7 and "`%s/`" % KEY_TARGET in s7
    assert "/run/field/keys/svc-<name>.key" in s7
    assert "<home>/.field-local/keys/svc-<name>/svc-<name>.key" in s7
    # the withdrawn single-file habits (operators file AND key file) are not offered anywhere
    for old in ("cat new.json >", "/run/field/operators.json", "FIELD_OPERATORS_FILE", "operators.empty.json",
                "Edit IN PLACE", OLD_KEY_TARGET, "operator-key.empty", "--force-recreate"):
        assert old not in s7, old
    assert not re.search(r"FIELD_OPERATOR_KEY_[A-Z_]*_FILE", s7)
    assert not re.search(r"\bcat\s+[^\n`]*>\s*\S*operators\.json", s7)
