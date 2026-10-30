"""C-638 (reviewer C-585 on PR 328, F-C585-1/-2/-4): the resolved-model check keeps its exit contract on a shape it
does not know, resolves the repository root with --realpath, says what it does not read, and the four survivors of
the review (a dict env_file that is allowed, a relative head of a string volume, the --realpath flag through the CLI, a
docker timeout) are pinned."""
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


def run(args, stdin=""):
    return subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), *args], input=stdin, capture_output=True,
                          text=True, timeout=60)


def model(**service):
    return json.dumps({"services": {"s": service}})


# --- F-C585-1: an unexpected shape is exit 3 with one line, never a traceback, never 1 or argparse's 2 --------------------


@pytest.mark.parametrize("service", [
    {"env_file": 5}, {"env_file": True}, {"build": ["a", "b"]}, {"build": 5}, {"volumes": 5}, {"volumes": {"a": 1}},
    {"build": {"context": ".", "additional_contexts": [5]}}, {"build": {"context": "/srv-fixture/checkout", "additional_contexts": 7}},
])
def test_a_service_shape_the_tool_does_not_know_is_exit_3_without_a_traceback(service):
    r = run(["--repo-root", REPO, "-"], model(**service))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "Traceback" not in r.stderr and "does not know" in r.stdout and "not checked" in r.stdout


@pytest.mark.parametrize("doc", [
    {"services": {"s": {}}, "volumes": ["a"]}, {"services": {"s": {}}, "secrets": ["a"]}, {"services": {"s": {}}, "configs": 3},
])
def test_a_top_level_shape_the_tool_does_not_know_is_exit_3_without_a_traceback(doc):
    r = run(["--repo-root", REPO, "-"], json.dumps(doc))
    assert r.returncode == 3 and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def test_a_model_that_is_refused_is_still_exit_2_and_a_clean_one_exit_0():
    assert run(["--repo-root", REPO, "-"], model(volumes=[{"type": "bind", "source": "/etc", "target": "/x"}])).returncode == 2
    assert run(["--repo-root", REPO, "-"], model(volumes=[{"type": "tmpfs", "target": "/x"}])).returncode == 0


@pytest.mark.parametrize("args", [[], ["--repo-root"], ["-"], ["--bogus", "--repo-root", REPO, "-"]])
def test_a_usage_error_is_exit_3_not_argparses_2_which_means_refused(args):
    r = run(args)
    assert r.returncode == 3 and "usage error" in r.stdout and "usage:" in r.stderr, (r.returncode, r.stdout, r.stderr)


def test_the_exit_contract_is_stated_in_the_tool():
    doc = crc.__doc__
    assert "3 the tool could not do its job" in doc and "usage errors are 3 too" in doc


# --- F-C585-1: --realpath resolves the repository root too ---------------------------------------------------------------


POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="the tool reads POSIX paths (a model names the Linux host's files)")


@POSIX_ONLY
def test_a_checkout_reached_through_a_symlink_is_not_refused_wholesale_under_realpath(tmp_path):
    real = tmp_path / "real-checkout"
    (real / "data").mkdir(parents=True)
    link = tmp_path / "link-to-checkout"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create symlinks")
    source = str(link / "data")
    doc = model(volumes=[{"type": "bind", "source": source, "target": "/x"}])
    r = run(["--repo-root", str(link), "--realpath", "-"], doc)
    assert r.returncode == 0, (r.stdout, r.stderr)
    r = run(["--repo-root", str(link), "-"], doc)                       # without the flag: judged by spelling, also clean
    assert r.returncode == 0


@POSIX_ONLY
def test_the_realpath_flag_is_wired_through_the_command_line(tmp_path):
    real = tmp_path / "checkout"
    (real / "data").mkdir(parents=True)
    link = real / "data" / "link"
    try:
        os.symlink("/etc", link)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create symlinks")
    doc = model(volumes=[{"type": "bind", "source": str(link), "target": "/x"}])
    assert run(["--repo-root", str(real), "-"], doc).returncode == 0                       # judged by its spelling
    r = run(["--repo-root", str(real), "--realpath", "-"], doc)                           # followed: /etc is on the denylist
    assert r.returncode == 2 and "denylist" in r.stdout


# --- F-C585-4: the survivors ---------------------------------------------------------------------------------------------


def test_a_dict_env_file_inside_the_repository_is_allowed_and_one_outside_is_refused():
    ok = {"services": {"s": {"env_file": {"path": REPO + "/integration/demo/ok.env", "required": False}}}}
    assert crc.check_model(ok, REPO) == []
    bad = {"services": {"s": {"env_file": {"path": "/etc/passwd"}}}}
    assert crc.check_model(bad, REPO) != []
    both = {"services": {"s": {"env_file": [{"path": REPO + "/a.env"}, "/etc/shadow"]}}}
    assert len(crc.check_model(both, REPO)) == 1


@pytest.mark.parametrize("head", ["./x", "../x", "~/x", "$HOME/x"])
def test_a_string_form_volume_with_a_relative_or_variable_head_is_refused(head):
    doc = {"services": {"s": {"volumes": [f"{head}:/y"]}}}
    problems = crc.check_model(doc, REPO)
    assert len(problems) == 1 and "volume" in problems[0], problems


def test_a_string_form_named_volume_and_tmpfs_are_not_binds():
    doc = {"services": {"s": {"volumes": ["data:/y", "tmpfs:/z", "volume:/w"]}}}
    assert crc.check_model(doc, REPO) == []


def test_a_docker_timeout_is_exit_3_not_a_pass_or_a_crash(monkeypatch, capsys):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=120)

    monkeypatch.setattr(crc.subprocess, "run", boom)
    assert crc.main(["--repo-root", REPO, "--run-compose", "a.yml"]) == 3
    assert "could not read the model" in capsys.readouterr().out


def test_a_docker_that_is_not_installed_is_exit_3(monkeypatch, capsys):
    def missing(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(crc.subprocess, "run", missing)
    assert crc.main(["--repo-root", REPO, "--run-compose", "a.yml"]) == 3


# --- F-C585-2: the scope is stated ------------------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", ["does NOT read", "build.dockerfile", "build.ssh", "build.cache_to", "devices",
                                    "develop.watch[].path", "volumes_from", "ANY `scheme:` prefix", "the key allowlist"])
def test_the_tool_says_which_keys_it_does_not_read(phrase):
    assert phrase in crc.__doc__


def test_the_unread_keys_really_are_unread_by_this_tool():
    """The statement above is true today: each of these is accepted by the resolved check (the static pins refuse them)."""
    doc = {"services": {"s": {
        "build": {"context": REPO, "dockerfile": "/etc/passwd", "ssh": ["default=/root/.ssh/id_rsa"],
                  "cache_to": ["type=local,dest=/etc/c"]},
        "devices": ["/dev/mem"], "volumes_from": ["container:x"],
        "develop": {"watch": [{"path": "/etc", "action": "sync"}]},
    }}}
    assert crc.check_model(doc, REPO) == []


# --- C-723 (cloud/reviewer C-698 on PR 353) -------------------------------------------------------------------------------


def test_text_that_is_not_utf8_is_exit_3_without_a_traceback(tmp_path):
    f = tmp_path / "model.bin"
    f.write_bytes(b"\xff\xfe\x00bad")
    for extra in ([], ["--realpath"]):
        r = run(["--repo-root", REPO, *extra, str(f)])
        assert r.returncode == 3 and "Traceback" not in r.stderr and "could not read the model" in r.stdout, (r.stdout, r.stderr)


def test_stdin_that_is_not_utf8_is_exit_3_without_a_traceback():
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input=b"\xff\xfe\x00bad", capture_output=True, timeout=60)
    assert r.returncode == 3 and b"Traceback" not in r.stderr


@pytest.mark.parametrize("value", [5, True, None, [], ["/etc"], {"a": 1}, 1.5])
def test_a_bind_source_that_is_not_a_string_is_a_refusal_not_a_clean_pass(value):
    doc = {"services": {"s": {"volumes": [{"type": "bind", "source": value, "target": "/x"}]}}}
    problems = crc.check_model(doc, REPO)
    assert len(problems) == 1 and "is not a string" in problems[0], problems
    r = run(["--repo-root", REPO, "-"], json.dumps(doc))
    assert r.returncode == 2 and "is not a string" in r.stdout


def test_a_sourceless_volume_is_still_not_a_bind():
    doc = {"services": {"s": {"volumes": [{"type": "tmpfs", "target": "/x"}, {"type": "volume", "source": "data", "target": "/y"}]}}}
    assert crc.check_model(doc, REPO) == []
    assert crc.check_model({"services": {"s": {"volumes": [{"type": "bind", "source": REPO + "/ok", "target": "/x"}]}}}, REPO) == []


@pytest.mark.parametrize("text", ["[]", "[1, 2]", "{}", "null", "services: 5", "services: [a]", "5", '"x"', "&a [*a]", ""])
def test_every_text_that_is_not_a_compose_model_is_exit_3_not_a_refusal(text):
    r = run(["--repo-root", REPO, "-"], text)
    assert r.returncode == 3 and "Traceback" not in r.stderr, (text, r.returncode, r.stdout)
    assert "REFUSED" not in r.stdout


def test_check_model_raises_for_a_model_with_no_services():
    with pytest.raises(ValueError, match="no services"):
        crc.check_model({"volumes": {}}, REPO)


@pytest.mark.parametrize("flag", ["-I", "-P"])
def test_the_sibling_import_works_under_the_safe_path_modes(flag):
    r = subprocess.run([sys.executable, flag, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input=model(volumes=[{"type": "tmpfs", "target": "/x"}]), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "Traceback" not in r.stderr, (r.returncode, r.stdout, r.stderr)


def test_the_sibling_import_works_with_pythonsafepath_set():
    env = {**os.environ, "PYTHONSAFEPATH": "1"}
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input=model(volumes=[{"type": "tmpfs", "target": "/x"}]), capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0 and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def test_the_out_of_scope_items_are_stated_in_the_tool():
    doc = crc.__doc__
    assert "Out of scope, stated" in doc and "trusted as given" in doc and "--repo-root /tmp" in doc and "`--help` exits 0" in doc
    assert "text that is not UTF-8" in doc and "a bind source that is not a string" in doc


def test_a_root_outside_the_repository_is_trusted_as_given_and_that_is_documented():
    """Pins the stated limit: the tool does not check that the root is a checkout."""
    doc = {"services": {"s": {"volumes": [{"type": "bind", "source": "/tmp/data", "target": "/x"}]}}}
    assert crc.check_model(doc, "/tmp") == []
    assert crc.check_model(doc, "/srv-fixture/checkout") != []
    assert crc.check_model(doc, "/") != []                           # a root of "/" refuses everything: fail closed
