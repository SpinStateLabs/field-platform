"""C-715 (reviewers C-640 on PR 345 and C-648 on PR 328/353): the two compose layers judge the same names, the resolved
model checks what the static pins check (namespaces, privileged, devices, volumes_from, dockerfile, build schemes),
an empty model is not a clean pass, `--run-compose` passes `--profile "*"`, and the static key check never crashes on
a shape it does not know."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import compose_bind_rules as rules  # noqa: E402
import compose_resolved_check as crc  # noqa: E402
import test_compose_resolved_bind_c512 as c512  # noqa: E402
import test_compose_static_pins as pins  # noqa: E402

REPO = c512.REPO


def judged(**service):
    return crc.check_model({"services": {"s": service}}, REPO)


# --- the shared name rule (F-C640-2, F-C648-5) -----------------------------------------------------------------------------


@pytest.mark.parametrize("names", [[".git"], ["a", ".GIT", "b"], [".Git", "config"], ["x", ".env"], ["x", ".ENV"],
                                   ["x", ".env.local"], ["x", ".Env.Prod"]])
def test_name_problem_refuses_git_and_env_in_any_case(names):
    assert rules.name_problem(names)


@pytest.mark.parametrize("names", [["src"], ["a", "b.py"], [".envrc"], [".env", "x"], [".gitignore"], [], ["environment"]])
def test_name_problem_allows_the_stated_limits(names):
    assert rules.name_problem(names) is None


@pytest.mark.parametrize("name", [".GIT", ".Env", ".ENV.local"])
def test_the_static_pins_and_the_resolved_check_agree_on_case(name):
    assert pins._binds_forbidden_host_path(f"./{name}", kind="file")
    assert judged(volumes=[{"type": "bind", "source": f"{REPO}/{name}", "target": "/x"}])


# --- the resolved model: host-level options (F-C640-6) ---------------------------------------------------------------------


@pytest.mark.parametrize("option", sorted(rules.NAMESPACE_OPTIONS))
def test_a_resolved_namespace_option_is_judged(option):
    assert judged(**{option: "host"}), option


@pytest.mark.parametrize("option", sorted(rules.NAMESPACE_OPTIONS))
def test_a_non_string_namespace_option_is_a_violation(option):
    assert any("not a string" in v for v in judged(**{option: 5}))


def test_privileged_devices_and_volumes_from_are_refused():
    assert any("privileged" in v for v in judged(privileged=True))
    assert any("devices" in v for v in judged(devices=["/dev/mem"]))
    assert any("volumes_from" in v for v in judged(volumes_from=["container:x"]))
    assert judged(privileged=False, devices=[], volumes_from=[]) == []


# --- build.dockerfile and schemes (F-C648-1/-2) ----------------------------------------------------------------------------


def test_a_resolved_dockerfile_is_read_relative_to_the_context():
    out = judged(build={"context": REPO, "dockerfile": "../../etc/passwd"})
    assert out and any("dockerfile" in v for v in out)
    assert judged(build={"context": REPO, "dockerfile": "Dockerfile"}) == []


def test_an_absolute_dockerfile_outside_the_repository_is_refused():
    assert any("dockerfile" in v for v in judged(build={"context": REPO, "dockerfile": "/etc/passwd"}))


def test_dockerfile_inline_and_a_non_string_dockerfile_are_refused():
    assert any("dockerfile_inline" in v for v in judged(build={"context": REPO, "dockerfile_inline": "FROM x"}))
    assert any("not a string" in v for v in judged(build={"context": REPO, "dockerfile": 5}))


@pytest.mark.parametrize("value", ["file:///etc", "oci-layout:///etc", "https://example.invalid/x.git", "git://h/r"])
def test_an_additional_context_scheme_other_than_docker_image_is_refused(value):
    out = judged(build={"context": REPO, "additional_contexts": {"c": value}})
    assert any("scheme other than docker-image://" in v for v in out), out


def test_a_docker_image_context_and_a_non_string_context():
    assert judged(build={"context": REPO, "additional_contexts": {"c": "docker-image://alpine"}}) == []
    assert any("not a string" in v for v in judged(build={"context": REPO, "additional_contexts": {"c": 5}}))


# --- empty model and tmpfs device (F-C648-7/-8) ----------------------------------------------------------------------------


def test_an_empty_service_map_is_not_a_clean_pass():
    with pytest.raises(ValueError, match="empty service map"):
        crc.check_model({"services": {}}, REPO)


def test_an_empty_service_map_is_exit_3_through_the_cli():
    import subprocess
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input='{"services": {}}', capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "Traceback" not in r.stderr


@pytest.mark.parametrize("opts", [{"type": "tmpfs", "device": "tmpfs"}, {"device": "tmpfs"}])
def test_a_tmpfs_volume_device_is_not_a_path(opts):
    doc = {"services": {"s": {"image": "x"}}, "volumes": {"v": {"driver_opts": opts}}}
    assert crc.check_model(doc, REPO) == []


def test_a_real_device_path_is_still_judged():
    doc = {"services": {"s": {"image": "x"}}, "volumes": {"v": {"driver_opts": {"type": "none", "device": "/etc"}}}}
    assert crc.check_model(doc, REPO)


# --- --profile "*" (F-C648-3) ----------------------------------------------------------------------------------------------


def test_run_compose_passes_every_profile(monkeypatch):
    seen = []

    class Done:
        returncode, stdout, stderr = 0, '{"services": {"s": {"image": "x"}}}', ""

    monkeypatch.setattr(crc.subprocess, "run", lambda cmd, **kw: seen.append(list(cmd)) or Done())
    crc.run_compose_config(["a.yml", "b.yml"], project_dir="/p")
    assert seen == [["docker", "compose", "-f", "a.yml", "-f", "b.yml", "--project-directory", "/p", "--profile", "*",
                     "config", "--format", "json"]]


# --- the static key check never crashes (F-C640-5, F-C640-4) ---------------------------------------------------------------


@pytest.mark.parametrize("text", ["- a\n- b\n", "services: 5\n", "services:\n  s: 5\n", "services:\n  s:\n    build: [a]\n",
                                  "services:\n  s:\n    build:\n      context: 5\n",
                                  "services:\n  s:\n    env_file: 5\n",
                                  "services:\n  s:\n    env_file:\n      - path: 5\n",
                                  "services:\n  s:\n    build:\n      context: .\n      additional_contexts: 5\n",
                                  "services:\n  s:\n    build:\n      context: .\n      additional_contexts: [5]\n",
                                  "services:\n  s:\n    volumes:\n      - type: bind\n        source: 5\n        target: /x\n"])
def test_an_unknown_shape_is_a_violation_never_an_exception(text):
    out = pins.key_violations(text, "services: {}\n")
    assert out, text


def test_a_string_build_is_read_as_a_context():
    assert pins.key_violations("services:\n  s:\n    build: .\n", "services: {}\n") == []


def test_a_dockerfile_is_read_relative_to_the_context_by_the_static_pins():
    text = "services:\n  s:\n    build:\n      context: ../..\n      dockerfile: ../../secret\n"
    assert any("dockerfile" in v for v in pins.key_violations(text, "services: {}\n"))
    ok = "services:\n  s:\n    build:\n      context: .\n      dockerfile: Dockerfile\n"
    assert pins.key_violations(ok, "services: {}\n") == []


# --- the docstring says what is not wired and not read ---------------------------------------------------------------------


@pytest.mark.parametrize("phrase", ["NOT WIRED", "Operator check", "C-715 narrowed the list", "--profile"])
def test_the_docstring_is_honest_about_scope(phrase):
    assert phrase in crc.__doc__
