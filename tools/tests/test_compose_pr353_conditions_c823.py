"""C-823 (reviewer C-735 on PR 353, F-C735-1..-5 and the survivors): `--realpath` resolves the allowed roots and the
source string as written, every key kind is checked for text, a non-mapping service is exit 3, the eight real survivors
of the review are pinned, and the posture limit is stated."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import compose_resolved_check as crc  # noqa: E402
import test_compose_resolved_bind_c512 as c512  # noqa: E402

REPO = c512.REPO
SCRIPT = str(TOOLS / "compose_resolved_check.py")
REAL = os.path.realpath
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX paths: the GX10 (Linux) is authoritative")


def link(target, name):
    try:
        os.symlink(target, name)
    except (OSError, NotImplementedError):
        pytest.skip("this environment cannot create symlinks")


def judged(source, repo=REPO, realpath=None, kind="volume"):
    return crc.source_problem(source, repo, kind, realpath)


def run(args, stdin="", env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], input=stdin, capture_output=True, text=True, timeout=60,
                          env=env)


def model(**service):
    return json.dumps({"services": {"s": service}})


# --- F-C735-1: the allowed roots are resolved under --realpath ------------------------------------------------------------


@posix_only
def test_a_symlinked_allowed_root_still_allows_its_binds_under_realpath(tmp_path, monkeypatch):
    real = tmp_path / "real"
    (real / "caller-keys").mkdir(parents=True)
    link(real, tmp_path / "fakehome")
    root = str(tmp_path / "fakehome" / "caller-keys")
    monkeypatch.setattr(crc, "ALLOWED_ABSOLUTE_ROOTS", (root,))
    source = root + "/key1"
    assert judged(source) is None                                       # as written: allowed
    assert judged(source, realpath=REAL) is None                        # C-823: still allowed once the link is followed
    assert judged(str(real / "caller-keys" / "key1"), realpath=REAL) is None     # the resolved spelling too
    assert judged(str(real / "caller-keys" / "key1")) == "outside the repository and the allowed roots"


@posix_only
def test_an_allowed_root_behind_a_symlinked_parent_is_resolved_too(tmp_path, monkeypatch):
    (tmp_path / "store" / "caller-keys").mkdir(parents=True)
    link(tmp_path / "store", tmp_path / "parent")
    root = str(tmp_path / "parent" / "caller-keys")
    monkeypatch.setattr(crc, "ALLOWED_ABSOLUTE_ROOTS", (root,))
    assert judged(root + "/k", realpath=REAL) is None
    assert judged(str(tmp_path / "store" / "caller-keys" / "k"), realpath=REAL) is None


@posix_only
def test_a_source_outside_every_root_is_still_refused_under_realpath(tmp_path, monkeypatch):
    (tmp_path / "real").mkdir()
    link(tmp_path / "real", tmp_path / "fakehome")
    monkeypatch.setattr(crc, "ALLOWED_ABSOLUTE_ROOTS", (str(tmp_path / "fakehome"),))
    assert judged(str(tmp_path / "elsewhere" / "k"), realpath=REAL) == "outside the repository and the allowed roots"
    assert judged(str(tmp_path / "real") + "x/k", realpath=REAL) == "outside the repository and the allowed roots"


# --- F-C735-3: a `..` after a link is followed physically ------------------------------------------------------------------


@posix_only
def test_dot_dot_after_a_link_out_of_the_repository_is_not_collapsed_first(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside" / "sub").mkdir(parents=True)
    link(tmp_path / "outside" / "sub", repo / "link_out")
    root = REAL(str(repo))
    source = root + "/link_out/../data/f"
    assert judged(source, root) is None                                  # lexically `<repo>/data/f`: allowed as written
    assert judged(source, root, REAL) == "outside the repository and the allowed roots"     # physically `<outside>/data/f`


@posix_only
def test_dot_dot_after_a_link_to_etc_is_refused_under_realpath(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    link("/etc", repo / "link_etc")
    root = REAL(str(repo))
    assert judged(root + "/link_etc/../x", root, REAL)
    assert judged(root + "/link_etc/passwd", root, REAL) == "on the denylist"


@posix_only
def test_a_plain_dot_dot_that_stays_inside_is_still_allowed_under_realpath(tmp_path):
    repo = tmp_path / "repo"
    (repo / "a" / "b").mkdir(parents=True)
    root = REAL(str(repo))
    assert judged(root + "/a/b/../c", root, REAL) is None


# --- F-C735-2: every key kind is checked for text; a service that is not a mapping is exit 3 -------------------------------


@pytest.mark.parametrize("doc", [
    {"services": {"s": {"image": "x"}}, "secrets": {"k": {"file": ["/etc/shadow"]}}},
    {"services": {"s": {"image": "x"}}, "secrets": {"k": {"file": 5}}},
    {"services": {"s": {"image": "x"}}, "configs": {"k": {"file": {"a": 1}}}},
    {"services": {"s": {"image": "x"}}, "volumes": {"v": {"driver_opts": {"device": ["/etc"]}}}},
    {"services": {"s": {"image": "x"}}, "volumes": {"v": {"driver_opts": {"device": 5}}}},
    {"services": {"s": {"build": {"context": ["/etc"]}}}},
    {"services": {"s": {"build": {"context": 5}}}},
    {"services": {"s": {"env_file": [{"path": 5}]}}},
    {"services": {"s": {"env_file": [5]}}},
])
def test_a_non_string_path_of_any_kind_is_refused_never_clean(doc):
    out = crc.check_model(doc, REPO)
    assert out and any("not a string" in line for line in out), out


@pytest.mark.parametrize("service", ["a string", ["a", "list"], None, 5])
def test_a_service_that_is_not_a_mapping_is_not_an_empty_service(service):
    with pytest.raises(ValueError, match="not a mapping"):
        crc.check_model({"services": {"s": service}}, REPO)
    r = run(["--repo-root", REPO, "-"], json.dumps({"services": {"s": service}}))
    assert r.returncode == 3 and "Traceback" not in r.stderr


def test_an_env_file_that_is_a_number_is_a_shape_error_not_a_type_error():
    with pytest.raises(ValueError, match="env_file"):
        crc.check_model({"services": {"s": {"env_file": 5}}}, REPO)


def test_a_build_without_a_context_key_is_not_called_a_non_string():
    assert crc.check_model({"services": {"s": {"build": {"args": {"A": "1"}}}}}, REPO) == []


def test_an_env_file_that_is_a_number_is_exit_3():
    r = run(["--repo-root", REPO, "-"], model(env_file=5))
    assert r.returncode == 3 and "Traceback" not in r.stderr


def test_a_mapping_service_and_the_good_shapes_stay_clean():
    assert crc.check_model({"services": {"s": {"image": "x", "env_file": ["/srv-fixture/checkout/a.env"],
                                               "build": {"context": REPO}}}}, REPO) == []


# --- F-C735-4: the real survivors, pinned -----------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["/srv-fixture/checkout/a\nb", "/srv-fixture/checkout/a\x00b"])
def test_a_newline_or_a_nul_in_a_source_is_not_a_literal_path(source):
    assert judged(source) == "not a resolved literal path"


def test_a_socket_name_inside_the_repository_is_refused():
    assert judged(REPO + "/docker.sock") == "on the denylist"
    assert judged(REPO + "/sub/docker.sock") == "on the denylist"


@pytest.mark.parametrize("root", [REPO + "/", REPO + "//", REPO + "/x/..", REPO + "/./"])
def test_the_repo_root_is_normalised_before_the_comparison(root):
    assert judged(REPO + "/a", root) is None
    assert judged("/elsewhere/a", root) == "outside the repository and the allowed roots"


def test_envrc_is_allowed_and_env_dot_anything_is_not():
    assert judged(REPO + "/.envrc") is None
    assert judged(REPO + "/.env") == "an .env file"
    assert judged(REPO + "/.env.local") == "an .env file"
    assert judged(REPO + "/.environment") is None


def test_a_model_file_is_read_as_utf8_whatever_the_locale(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"services": {"sā": {"image": "x"}}}, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C", LANG="C")
    r = run(["--repo-root", REPO, str(f)], env=env)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


def test_the_all_clear_line_is_never_printed_after_a_refusal():
    refused = run(["--repo-root", REPO, "-"], model(volumes=[{"type": "bind", "source": "/etc", "target": "/x"}]))
    assert refused.returncode == 2 and "REFUSED" in refused.stdout and "every bind source is allowed" not in refused.stdout
    clean = run(["--repo-root", REPO, "-"], model(image="x"))
    assert clean.returncode == 0 and "every bind source is allowed" in clean.stdout and "REFUSED" not in clean.stdout


def test_a_failing_docker_is_exit_3_even_when_it_printed_a_model(monkeypatch, capsys):
    class Done:
        returncode, stdout, stderr = 1, '{"services": {"s": {"image": "x"}}}', "boom"

    monkeypatch.setattr(crc.subprocess, "run", lambda cmd, **kw: Done())
    with pytest.raises(RuntimeError, match="exited 1"):
        crc.run_compose_config(["a.yml"])
    assert crc.main(["--repo-root", REPO, "--run-compose", "a.yml"]) == 3
    assert "could not read the model" in capsys.readouterr().out


# --- F-C735-6: the sibling is found through a symlink to the script ---------------------------------------------------------


def test_a_symlink_to_the_script_in_another_directory_still_finds_its_sibling(tmp_path):
    (tmp_path / "bin").mkdir()
    link(SCRIPT, tmp_path / "bin" / "compose_resolved_check.py")
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "bin" / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input=model(image="x"), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ModuleNotFoundError" not in r.stderr, (r.stdout, r.stderr)


# --- the posture limit is stated (F-C735-5) ---------------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", ["Posture limit, stated", "cap_add", "security_opt", "sysctls", "last-wins",
                                    "allowed roots are resolved too"])
def test_the_docstring_states_the_posture_limit_and_the_realpath_reading(phrase):
    assert phrase in crc.__doc__
