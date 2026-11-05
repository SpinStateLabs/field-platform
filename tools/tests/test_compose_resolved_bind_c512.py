"""C-512 (Lane 10 C-492 structural gap): the C-453 bind-source allowlist applied to the RESOLVED compose model.

The static pins validate the DEFAULT of every `${VAR:-default}`; the estate's environment can still replace the
variable. `tools/compose_resolved_check.py` reads the text of `docker compose config` (as DATA: nothing here runs
docker) and applies the same rule to the resolved host paths. The acceptance test resolves the SHIPPED compose files
under an environment that points an estate-driven variable at a forbidden directory: the static check is green on
the same files and the resolved check is red. All paths below are made up; no estate value is in this file.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import compose_bind_rules as rules  # noqa: E402
import compose_resolved_check as crc  # noqa: E402
import test_compose_static_pins as static  # noqa: E402

REPO = "/srv-fixture/checkout"                      # a made-up checkout path (the repository root of the fixture)
PROJECT = REPO + "/integration/demo"                # compose resolves relative paths against the compose file's directory
KEYS = "/home/spinner/.field-local/caller-keys"


def _resolve(text: str, env: dict[str, str]) -> str:
    """`${NAME:-default}` / `${NAME-default}` / `${NAME}` with `env` (what `docker compose config` does, for the
    forms the shipped files use)."""
    def sub(m):
        name, op, default = m.group(1), m.group(2), m.group(3)
        value = env.get(name)
        if value is None or (op == ":-" and value == ""):
            return default or ""
        return value
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)([^}]*))?\}", sub, text)


def _absolute(path: str) -> str:
    return path if path.startswith("/") else crc.normal(PROJECT + "/" + path)


def resolved_model(env: dict[str, str] | None = None) -> dict:
    """What `docker compose -f base -f gb10 config` would print for the shipped files under `env`, for the keys the
    allowlist reads (long-syntax volumes with absolute sources, secrets, configs, build contexts)."""
    env = env or {}
    base, gb10 = (static.DEMO / "docker-compose.yml").read_text(encoding="utf-8"), (static.DEMO / "docker-compose.gb10.yml").read_text(encoding="utf-8")
    services = {}
    for name, svc in static._services(base, gb10).items():
        out = {}
        vols = []
        for vol in svc.get("volumes") or []:
            if isinstance(vol, dict):
                src = vol.get("source")
                vols.append({**vol, "source": _absolute(_resolve(src, env))} if vol.get("type") in (None, "bind") and isinstance(src, str) and re.match(r"^[./$~/]", src) else vol)
                continue
            parts = _resolve(str(vol), env).split(":")
            head = parts[0]
            if head.startswith(("/", ".")):
                vols.append({"type": "bind", "source": _absolute(head), "target": parts[1]})
            else:
                vols.append({"type": "volume", "source": head, "target": parts[1]})
        if vols:
            out["volumes"] = vols
        build = svc.get("build")
        if build:
            ctx = build if isinstance(build, str) else build.get("context")
            out["build"] = {"context": _absolute(_resolve(ctx, env))}
        services[name] = out
    model = {"name": "demo", "services": services}
    for section in ("secrets", "configs"):
        items = static._top_level_section(base, gb10, section)
        if items:
            model[section] = {k: ({**v, "file": _absolute(_resolve(v["file"], env))} if isinstance(v, dict) and "file" in v else v) for k, v in items.items()}
    return model


# ---- the shared rules --------------------------------------------------------------------------------------------

def test_the_static_pins_and_the_gate_check_share_one_definition_of_the_rules():
    for name in ("ALLOWED_ABSOLUTE_ROOTS", "FORBIDDEN_BIND_TREES", "FORBIDDEN_BIND_EXACT", "FORBIDDEN_HOME_DIRS",
                 "FORBIDDEN_HOME_PARENTS", "A_HOME", "RUNTIME_SOCKET"):
        assert getattr(static, name) is getattr(rules, name) is getattr(crc, name), name


# ---- the shipped files, resolved ---------------------------------------------------------------------------------

def test_the_shipped_compose_files_resolved_with_their_defaults_are_allowed():
    model = resolved_model()
    assert crc.check_model(model, REPO) == []
    # a scan that finds no bind source would pass anything: the fixture must really carry the estate-driven binds
    sources = [v["source"] for s in model["services"].values() for v in s.get("volumes", []) if v["type"] == "bind"]
    assert len(sources) >= 15 and any(x.startswith(KEYS + "/") for x in sources) and any(x.startswith(PROJECT + "/operator") for x in sources)


ESTATE_VARIABLES = ["FIELD_OPERATORS_DIR", "FIELD_OPERATOR_KEY_DIR_REGISTRY", "FIELD_OPERATOR_KEY_DIR_DELEGATION",
                    "FIELD_OPERATOR_KEY_DIR_KILLSWITCH", "FIELD_OPERATOR_KEY_DIR_LIFECYCLE", "CLAUDE_APPROVER_SECRETS_DIR",
                    "FIELD_CALLER_KEYS_DIR"]


@pytest.mark.parametrize("variable", ESTATE_VARIABLES)
@pytest.mark.parametrize("value", ["/etc", "/home/spinner/.ssh", "/", "/home/spinner", "/var/run/some-runtime"])
def test_a_forbidden_value_of_an_estate_variable_is_red_where_the_static_check_is_green(variable, value):
    base, gb10 = static._texts()[1:]
    static.check_compose(base, gb10)                               # the static check sees only the defaults: green
    problems = crc.check_model(resolved_model({variable: value}), REPO)
    assert problems, f"{variable}={value}: the resolved check missed it"
    assert any(value.rstrip("/") in p or "repository" in p or "denylist" in p for p in problems), problems


@pytest.mark.parametrize("variable", ESTATE_VARIABLES)
def test_an_allowed_value_of_an_estate_variable_stays_green(variable):
    ok = KEYS + "/another-service" if variable == "FIELD_CALLER_KEYS_DIR" else REPO + "/integration/demo/another-dir"
    assert crc.check_model(resolved_model({variable: ok}), REPO) == []


def test_an_estate_variable_that_replaces_the_allowed_root_with_another_directory_is_red():
    # the class Lane 10 named: ${FIELD_CALLER_KEYS_DIR:-<allowed root>}/registry passes on its default
    assert crc.check_model(resolved_model({"FIELD_CALLER_KEYS_DIR": "/opt/elsewhere"}), REPO) != []
    assert crc.check_model(resolved_model({"FIELD_CALLER_KEYS_DIR": "/home/spinner/.field-local/other"}), REPO) != []


# ---- the rule, source by source -----------------------------------------------------------------------------------

@pytest.mark.parametrize("source", [
    PROJECT + "/operators", REPO + "/Caddyfile", REPO + "/integration/fly/Caddyfile", KEYS + "/registry",
    KEYS + "/registry/../delegation", "//srv-fixture//checkout/x",
])
def test_these_sources_are_allowed(source):
    assert crc.source_problem(source, REPO) is None


@pytest.mark.parametrize("source,why", [
    ("", "empty"), ("operators", "not absolute"), ("./operators", "not absolute"), ("~/x", "not absolute"),
    ("/srv-fixture/checkout/$X", "not a resolved literal path"), ("/a`b", "not a resolved literal path"),
    ("/etc", "denylist"), ("/etc/ssl", "denylist"), ("/", "denylist"), ("/home", "denylist"),
    ("/home/spinner", "denylist"), ("/home/spinner/.ssh", "denylist"), ("/home/spinner/.config", "denylist"),
    ("/var/run/docker.sock", "denylist"), ("/run/containerd/containerd.sock", "denylist"),
    ("/opt/elsewhere", "outside"), ("/srv-fixture/other", "outside"), ("/srv-fixture/checkout-evil/x", "outside"),
    (KEYS, "outside"), (KEYS + "-evil/x", "outside"), (KEYS + "/../x", "outside"),
    (REPO, "repository root"), (REPO + "/.git", "inside .git"), (REPO + "/a/.git/config", "inside .git"),
    (REPO + "/.env", ".env"), (REPO + "/integration/demo/.env.local", ".env"),
    (REPO + "/../../etc", "denylist"), (REPO + "/../etc", "outside"),
])
def test_these_sources_are_refused_with_a_reason(source, why):
    assert why in (crc.source_problem(source, REPO) or "")


def test_the_repository_root_is_allowed_only_as_a_build_context():
    assert crc.source_problem(REPO, REPO, "build-context") is None
    assert crc.source_problem(REPO, REPO, "volume") is not None
    assert crc.source_problem(REPO + "/.git", REPO, "build-context") is not None


def test_a_sourceless_volume_has_no_host_path():
    assert crc.source_problem(None, REPO) is None


# ---- the other keys that carry a host path -----------------------------------------------------------------------

def test_driver_opts_device_secrets_configs_env_file_and_build_contexts_are_judged():
    ok = {"services": {"a": {"image": "x"}}}
    assert crc.check_model(ok, REPO) == []
    cases = {
        "volumes": {"volumes": {"v": {"driver_opts": {"type": "none", "o": "bind", "device": "/etc"}}}},
        "secret": {"secrets": {"s": {"file": "/etc/shadow"}}},
        "config": {"configs": {"c": {"file": "/opt/x"}}},
        "env_file": {"services": {"a": {"env_file": [{"path": "/opt/x.env", "required": True}]}}},
        "env_file string": {"services": {"a": {"env_file": "/opt/x.env"}}},
        "build": {"services": {"a": {"build": {"context": "/etc"}}}},
        "build string": {"services": {"a": {"build": "/etc"}}},
        "additional": {"services": {"a": {"build": {"context": REPO, "additional_contexts": {"x": "/etc"}}}}},
        "additional list": {"services": {"a": {"build": {"context": REPO, "additional_contexts": ["x=/etc"]}}}},
        "string volume": {"services": {"a": {"volumes": ["/etc:/x:ro"]}}},
    }
    for name, extra in cases.items():
        model = {"services": {"a": {"image": "x"}}, **extra}
        if "services" in extra:
            model["services"] = extra["services"]
        assert crc.check_model(model, REPO) != [], name
    good = {"services": {"a": {"build": {"context": REPO, "additional_contexts": {"b": "docker-image://alpine", "c": "https://example.invalid/x.git"}}}}}
    assert crc.check_model(good, REPO) == []


def test_a_tmpfs_named_volume_and_a_volume_type_are_not_host_paths():
    model = {"services": {"a": {"volumes": [{"type": "tmpfs", "target": "/tmp"}, {"type": "volume", "source": "data", "target": "/d"}]}}}
    assert crc.check_model(model, REPO) == []


def test_text_that_is_not_a_compose_model_is_a_shape_error():
    # C-723: not a compose model is exit 3 ("a shape this tool does not know"), so check_model raises, main maps it
    for bad in (None, [], {}, {"services": []}, "services: x"):
        with pytest.raises(ValueError, match="no services"):
            crc.check_model(bad, REPO)


# ---- symlinks only with --realpath -------------------------------------------------------------------------------

def test_a_symlinked_source_is_followed_only_with_realpath(tmp_path):
    repo = tmp_path / "checkout"
    (repo / "data").mkdir(parents=True)
    link = repo / "data" / "link"
    link.symlink_to("/etc")
    assert crc.source_problem(str(link), str(repo)) is None                       # judged by its spelling
    assert "denylist" in crc.source_problem(str(link), str(repo), realpath=os.path.realpath)


# ---- the command line --------------------------------------------------------------------------------------------

def _run(args, stdin="", env=None):
    return subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), *args], input=stdin, capture_output=True,
                          text=True, timeout=60, env=env)


def test_the_cli_reads_json_from_stdin_and_from_a_file(tmp_path):
    clean = json.dumps(resolved_model())
    r = _run(["--repo-root", REPO, "-"], clean)
    assert r.returncode == 0 and "every bind source is allowed" in r.stdout
    bad = json.dumps(resolved_model({"FIELD_OPERATORS_DIR": "/etc"}))
    f = tmp_path / "model.json"
    f.write_text(bad)
    r = _run(["--repo-root", REPO, str(f)])
    assert r.returncode == 2 and "REFUSED" in r.stdout and "/etc" in r.stdout
    r = _run(["--repo-root", REPO, "-"], yaml.safe_dump(resolved_model({"FIELD_OPERATORS_DIR": "/etc"})))
    assert r.returncode == 2


def test_the_cli_says_when_the_model_cannot_be_read(tmp_path):
    assert _run(["--repo-root", REPO, str(tmp_path / "missing.json")]).returncode == 3
    assert _run(["--repo-root", REPO, "-"], "a: [unclosed").returncode == 3
    r = _run(["--repo-root", REPO, "-"], "{}")
    assert r.returncode == 3 and "does not know" in r.stdout          # C-723: not a compose model is exit 3, not a refusal


def _fake_docker(tmp_path, body: str, rc: int = 0):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "docker.calls"
    docker = bindir / "docker"
    docker.write_text("#!/bin/sh\necho \"$*\" >> \"%s\"\n[ %d -eq 0 ] && cat <<'EOF'\n%s\nEOF\nexit %d\n" % (log, rc, body, rc))
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}, log


def test_docker_runs_only_with_run_compose_and_only_for_config(tmp_path):
    env, log = _fake_docker(tmp_path, json.dumps(resolved_model({"FIELD_OPERATORS_DIR": "/etc"})))
    r = _run(["--repo-root", REPO, "-"], json.dumps(resolved_model()), env=env)       # stdin: docker is never called
    assert r.returncode == 0 and not log.exists()
    r = _run(["--repo-root", REPO, "--run-compose", "a.yml", "b.yml"], env=env)
    assert r.returncode == 2
    calls = log.read_text().splitlines()
    assert calls == ["compose -f a.yml -f b.yml config --format json"]


def test_a_failing_docker_is_exit_3_not_a_clean_pass(tmp_path):
    env, log = _fake_docker(tmp_path, "", rc=1)
    r = _run(["--repo-root", REPO, "--run-compose", "a.yml"], env=env)
    assert r.returncode == 3 and "REFUSED" not in r.stdout
