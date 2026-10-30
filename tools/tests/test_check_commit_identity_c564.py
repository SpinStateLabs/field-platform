"""C-564 (reviewer C-562 F-C562-1): the commit-identity guard.

The pure function runs over fixture log lines (made-up identities in a reserved example domain); the CLI runs against a
throwaway git repository. No real address appears in this file, and the messages must not echo a value.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_commit_identity", TOOLS / "check_commit_identity.py")
cci = importlib.util.module_from_spec(_spec)
sys.modules["check_commit_identity"] = cci
_spec.loader.exec_module(cci)

SHA = "0123456789abcdef0123456789abcdef01234567"
GOOD_NAME, GOOD_EMAIL = "Example Person", "12345+examplehandle@users.noreply.github.com"
BAD_ADDR = "someone.example@mail.example.invalid"          # made up; reserved .invalid domain


def line(an=GOOD_NAME, ae=GOOD_EMAIL, cn=GOOD_NAME, ce=GOOD_EMAIL, sha=SHA) -> str:
    return "\x1f".join([sha, an, ae, cn, ce])


def fields(text, **kw):
    return [(f.field, f.reason) for f in cci.check(text, **kw)]


def test_a_clean_log_has_no_findings():
    assert cci.check(line() + "\n" + line(sha="f" * 40)) == []


@pytest.mark.parametrize("email", [
    "12345+examplehandle@users.noreply.github.com", "examplehandle@users.noreply.github.com",
    "noreply@github.com", "noreply@anthropic.com"])
def test_the_accepted_no_reply_forms_pass(email):
    assert cci.check(line(ae=email, ce=email)) == []


def test_an_email_address_as_the_author_name_is_a_finding():
    assert fields(line(an=BAD_ADDR)) == [("author name", "is an email address")]


def test_an_email_address_as_the_committer_name_is_a_finding():
    assert fields(line(cn=BAD_ADDR)) == [("committer name", "is an email address")]


@pytest.mark.parametrize("name", ["someone@localhost", "a@b", "Example Person <someone@host>"])
def test_any_text_at_text_as_a_name_is_a_finding(name):
    assert fields(line(an=name)) == [("author name", "is an email address")]


@pytest.mark.parametrize("name", ["Example Person", "Example O'Person-Smith", "Agent (build)", "example-handle"])
def test_ordinary_names_pass(name):
    assert cci.check(line(an=name, cn=name)) == []


def test_an_ordinary_email_as_the_author_email_is_a_finding():
    assert fields(line(ae=BAD_ADDR)) == [("author email", "is not an accepted no-reply form")]


def test_an_ordinary_email_as_the_committer_email_is_a_finding():
    assert fields(line(ce=BAD_ADDR)) == [("committer email", "is not an accepted no-reply form")]


def test_all_four_fields_are_reported_for_one_commit():
    assert {f for f, _ in fields(line(an=BAD_ADDR, ae=BAD_ADDR, cn=BAD_ADDR, ce=BAD_ADDR))} == {
        "author name", "author email", "committer name", "committer email"}


@pytest.mark.parametrize("email", [
    "@users.noreply.github.com", "name@users.noreply.github.com.example.invalid", "x@notusers.noreply.github.com",
    "noreply@anthropic.com.example.invalid", "xnoreply@github.com", "name+tag@users.noreply.github.com"])
def test_lookalike_no_reply_forms_are_refused(email):
    assert fields(line(ae=email)) == [("author email", "is not an accepted no-reply form")]


@pytest.mark.parametrize("an,ae", [("", GOOD_EMAIL), ("   ", GOOD_EMAIL), (GOOD_NAME, ""), (GOOD_NAME, "  ")])
def test_an_empty_name_or_email_is_a_finding(an, ae):
    assert [r for _, r in fields(line(an=an, ae=ae))] == ["is empty"]


def test_an_allowed_domain_is_accepted_only_when_passed():
    corp = "person@corp.example.invalid"
    assert fields(line(ae=corp)) == [("author email", "is not an accepted no-reply form")]
    assert cci.check(line(ae=corp), allow_domains=["corp.example.invalid"]) == []
    assert cci.check(line(ae=corp), allow_domains=["@corp.example.invalid"]) == []
    assert fields(line(ae="x@evilcorp.example.invalid"), allow_domains=["corp.example.invalid"]) != []
    # the dots of the domain are literal: a lookalike with another character in their place is not accepted
    assert fields(line(ae="x@corpzexample.invalid"), allow_domains=["corp.example.invalid"]) != []
    assert fields(line(ae="x@sub.corp.example.invalid"), allow_domains=["corp.example.invalid"]) != []


def test_the_message_names_the_commit_and_the_field_but_never_the_value():
    (f,) = cci.check(line(an=BAD_ADDR, sha="abcdef" + "0" * 34))
    text = str(f)
    assert text.startswith("abcdef000000:") and "author name" in text
    assert BAD_ADDR not in text and "example.invalid" not in text and "@" not in text


def test_a_malformed_log_line_is_an_error():
    with pytest.raises(ValueError):
        cci.parse_log("only\x1ftwo")


def test_blank_lines_are_ignored():
    assert cci.check("\n" + line() + "\n\n") == []


# ---- the command line, against a throwaway repository ------------------------------------------------------------------


def _git(cwd, *args, env=None):
    base = {"PATH": os.environ["PATH"], "HOME": str(cwd), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", *args], cwd=cwd, env={**base, **(env or {})}, capture_output=True, text=True, check=True)


def _commit(cwd, name, email, msg):
    (Path(cwd) / "f.txt").write_text(msg)
    _git(cwd, "add", "f.txt")
    ident = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    _git(cwd, "commit", "-q", "-m", msg, env=ident)


def _run(cwd, *args, stdin=None):
    return subprocess.run([sys.executable, str(TOOLS / "check_commit_identity.py"), *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env={"PATH": os.environ["PATH"], "HOME": str(cwd),
                                                                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})


@pytest.fixture()
def repo(tmp_path):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git is not installed")
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, BAD_ADDR, BAD_ADDR, "old history with a bad identity")      # the base: not checked by default
    _git(tmp_path, "branch", "base")
    return tmp_path


def test_the_default_range_checks_only_new_commits(repo):
    _git(repo, "update-ref", "refs/remotes/origin/main", "base")
    _commit(repo, GOOD_NAME, GOOD_EMAIL, "a clean new commit")
    p = _run(repo)
    assert p.returncode == 0 and "clean" in p.stdout


def test_a_bad_new_commit_fails_and_names_no_value(repo):
    _git(repo, "update-ref", "refs/remotes/origin/main", "base")
    _commit(repo, BAD_ADDR, BAD_ADDR, "a new commit with a bad identity")
    p = _run(repo)
    assert p.returncode == 1
    assert "author name is an email address" in p.stdout and "committer email is not an accepted" in p.stdout
    assert BAD_ADDR not in p.stdout + p.stderr


def test_an_explicit_range_includes_the_old_commit(repo):
    p = _run(repo, "--range", "main")
    assert p.returncode == 1


def test_a_missing_base_is_an_error_not_a_pass(repo):
    p = _run(repo)             # no origin/main in this repository
    assert p.returncode == 2 and "git log failed" in p.stderr


def test_stdin_mode_and_allow_domain(repo):
    corp = "person@corp.example.invalid"
    assert _run(repo, "--stdin", stdin=line(ae=corp, ce=corp)).returncode == 1
    assert _run(repo, "--stdin", "--allow-domain", "corp.example.invalid", stdin=line(ae=corp, ce=corp)).returncode == 0
    assert _run(repo, "--stdin", stdin="garbage").returncode == 2


# ---- reviewer C-641: legitimate GitHub identities, disguised names, the range, the error paths -------------------------


@pytest.mark.parametrize("email", [
    "41898282+github-actions[bot]@users.noreply.github.com", "dependabot[bot]@users.noreply.github.com",
    "12345+octo_acme@users.noreply.github.com", "octo_acme@users.noreply.github.com", "12345+a-b_c-d@users.noreply.github.com"])
def test_github_bot_and_managed_user_no_reply_forms_pass(email):
    assert cci.check(line(ae=email, ce=email)) == []


@pytest.mark.parametrize("email", [
    "x[bot]x@users.noreply.github.com", "[bot]@users.noreply.github.com", "a[bot@users.noreply.github.com",
    "_x@users.noreply.github.com", "+handle@users.noreply.github.com", "12345+@users.noreply.github.com",
    "noreply@githubXcom", "usersXnoreplyXgithubXcom", "x@usersXnoreply.github.com", "x[bot][bot]@users.noreply.github.com",
    "x[bot]@users.noreply.github.com.example.invalid", "x[BOT]@users.noreply.github.com"])
def test_anything_that_is_not_a_no_reply_form_is_still_refused(email):
    assert fields(line(ae=email)) == [("author email", "is not an accepted no-reply form")]


def _at(kind):
    return {"ascii": "@", "fullwidth": "＠", "small": "﹫"}[kind]


@pytest.mark.parametrize("name", [
    "someone @mail.example.invalid", "someone @ mail.example.invalid", "someone@ mail.example.invalid",
    "someone@", "@mail.example.invalid", "someone @mail.example.invalid", "someone\t@mail.example.invalid",
    "someone" + _at("fullwidth") + "mail.example.invalid", "someone" + _at("small") + "mail.example.invalid",
    "some​one@mail.example.invalid", "some​" + _at("fullwidth") + "mail.example.invalid",
    "someone [at] mail.example.invalid", "someone(at)mail.example.invalid", "someone{at}mail", "someone[AT]mail",
    "someone%40mail.example.invalid", "someone&#64;mail.example.invalid", "someone&#x40;mail", "someone&commat;mail",
    "user@HOSTNAME", "mailto:someone@mail.example.invalid", "Name <someone@mail.example.invalid>"])
def test_disguised_and_spaced_address_names_are_findings(name):
    assert fields(line(an=name)) == [("author name", "is an email address")]


@pytest.mark.parametrize("name", [
    "Example Person", "José Muñoz", "Anna O'Neil-Smith", "李雷", "@handle", "Dev @ Team", "Meet at Noon",
    "github-actions[bot]", "Agent (build)", "example_handle", "Jürgen Böhm"])
def test_normal_names_are_not_findings(name):
    assert cci.check(line(an=name, cn=name)) == []


@pytest.mark.parametrize("rng", ["--output=/tmp/c564-must-not-exist", "-x", "--end-of-options", "", "a\nb", "a\x00b"])
def test_a_range_that_is_an_option_or_odd_is_refused(rng):
    with pytest.raises(ValueError):
        cci._git_log(rng)


def test_a_range_option_exits_2_and_writes_nothing(repo, tmp_path):
    target = tmp_path / "c564-must-not-exist.txt"
    p = _run(repo, f"--range=--output={target}")
    assert p.returncode == 2 and not target.exists()
    assert "revision range" in p.stderr and str(target) not in p.stdout


def test_a_log_with_the_wrong_column_order_is_an_error_that_echoes_nothing(repo):
    wrong = "\x1f".join([BAD_ADDR, "0123456789abcdef0123456789abcdef01234567", GOOD_NAME, GOOD_EMAIL, GOOD_EMAIL])
    p = _run(repo, "--stdin", stdin=wrong)
    out = p.stdout + p.stderr
    assert p.returncode == 2 and "commit id" in out
    assert not any(BAD_ADDR[i:i + 6] in out for i in range(len(BAD_ADDR) - 5))


def test_a_six_field_line_is_an_error_that_echoes_nothing(repo):
    bad = line() + "\x1f" + BAD_ADDR
    p = _run(repo, "--stdin", stdin=bad)
    out = p.stdout + p.stderr
    assert p.returncode == 2 and "five fields" in out
    assert not any(BAD_ADDR[i:i + 6] in out for i in range(len(BAD_ADDR) - 5))


def test_the_summary_counts_commits_not_findings(repo):
    two = line(an=BAD_ADDR, ae=BAD_ADDR, cn=BAD_ADDR, ce=BAD_ADDR) + "\n" + line(an=BAD_ADDR, sha="f" * 40)
    p = _run(repo, "--stdin", stdin=two)
    assert p.returncode == 1 and "2 commit(s)" in p.stderr
    assert len(p.stdout.splitlines()) == 5


def test_a_non_hex_commit_id_is_refused_in_parse_log():
    with pytest.raises(ValueError, match="commit id"):
        cci.parse_log(line(sha="g" * 40))
    with pytest.raises(ValueError, match="commit id"):
        cci.parse_log(line(sha="abc"))
    assert cci.parse_log(line(sha="a" * 64))      # a sha256 object name is accepted


@pytest.mark.parametrize("name,want", [
    ("some\u200bone [a\u200bt] mail", "is an email address"),        # a zero-width character inside the at spelling
    ("someone [\u200bat] mail", "is an email address"),
    ("\u200b", "is empty"), ("\u200b\u200d", "is empty"), (" \u2060 ", "is empty")])
def test_format_characters_are_dropped_before_the_rules_run(name, want):
    assert fields(line(an=name)) == [("author name", want)]
