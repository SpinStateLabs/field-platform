"""C-564 (reviewer C-562 F-C562-1): the commit-identity guard.

The pure function runs over fixture log lines (made-up identities in a reserved example domain); the CLI runs against a
throwaway git repository. No real address appears in this file, and the messages must not echo a value.
"""
from __future__ import annotations

import importlib.util
import os
import re
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
    ("some\u200bone [a\u200bt] mail.example", "is an email address"),        # a zero-width character inside the at spelling
    ("someone [\u200bat] mail.example", "is an email address"),
    ("\u200b", "is empty"), ("\u200b\u200d", "is empty"), (" \u2060 ", "is empty")])
def test_format_characters_are_dropped_before_the_rules_run(name, want):
    assert fields(line(an=name)) == [("author name", want)]


# ---- reviewer C-677: email case rules, output shape, an empty range prints its count --------------------------------------


@pytest.mark.parametrize("email", [
    "12345+Example-Handle@USERS.NOREPLY.GITHUB.COM", "examplehandle@Users.NoReply.GitHub.Com", "x[bot]@USERS.NOREPLY.GITHUB.COM",
    "noreply@GITHUB.COM", "noreply@Anthropic.Com"])
def test_the_domain_of_an_accepted_form_is_case_insensitive(email):
    assert cci.check(line(ae=email, ce=email)) == []


@pytest.mark.parametrize("email", [
    "NOREPLY@github.com", "NoReply@anthropic.com", "x[BOT]@users.noreply.github.com", "x@GITHUBXCOM", "noreply@GITHUB.COM.example.invalid",
    "x@USERSXNOREPLYXGITHUBXCOM"])
def test_the_rest_of_an_accepted_form_is_case_sensitive_and_lookalikes_stay_refused(email):
    assert fields(line(ae=email)) == [("author email", "is not an accepted no-reply form")]


def test_an_allowed_domain_is_case_insensitive_too():
    assert cci.check(line(ae="person@CORP.Example.INVALID"), allow_domains=["corp.example.invalid"]) == []
    assert cci.check(line(ae="person@corp.example.invalid"), allow_domains=["CORP.EXAMPLE.INVALID"]) == []
    assert fields(line(ae="person@corpzexample.invalid"), allow_domains=["CORP.EXAMPLE.INVALID"]) != []


FINDING_LINE = re.compile(r"[0-9a-f]{12}: (?:author|committer) (?:name|email) (?:is an email address|is not an accepted no-reply form|is empty)")
SUMMARY_LINE = re.compile(r"[0-9]+ commit\(s\) carry an identity that must not be public; set user\.name and user\.email to the "
                          r"repository identity \(a no-reply address\) before committing")


def test_every_output_line_is_a_short_sha_a_field_and_a_reason_and_nothing_else(repo):
    log = "\n".join([
        line(an=BAD_ADDR, ae=BAD_ADDR, cn=BAD_ADDR, ce=BAD_ADDR),
        line(an="", ae=" ", sha="a" * 40),
        line(an="someone [at] mail.example.invalid", ae="x@USERSXNOREPLY.github.com", sha="b" * 64),
    ])
    p = _run(repo, "--stdin", stdin=log)
    assert p.returncode == 1
    out = p.stdout.splitlines()
    assert out and all(FINDING_LINE.fullmatch(ln) for ln in out), out
    assert SUMMARY_LINE.fullmatch(p.stderr.strip()), p.stderr
    assert not any(BAD_ADDR[i:i + 6] in p.stdout + p.stderr for i in range(len(BAD_ADDR) - 5))
    assert "a" * 13 not in p.stdout and "b" * 13 not in p.stdout          # never more than 12 characters of the id


@pytest.mark.parametrize("n,words", [(0, "checked 0 commits"), (1, "checked 1 commit)"), (2, "checked 2 commits")])
def test_the_clean_line_says_how_many_commits_were_checked(repo, n, words):
    log = "\n".join(line(sha=f"{i:040x}") for i in range(n))
    p = _run(repo, "--stdin", stdin=log)
    assert p.returncode == 0 and "clean" in p.stdout and words in p.stdout, p.stdout


def test_an_empty_range_in_a_repository_prints_its_count_not_a_bare_clean(repo):
    p = _run(repo, "--range", "main..main")
    assert p.returncode == 0 and "checked 0 commits" in p.stdout


def test_the_count_is_of_all_commits_checked_not_only_the_clean_ones(repo):
    p = _run(repo, "--stdin", stdin=line(an=BAD_ADDR) + "\n" + line(sha="c" * 40))
    assert p.returncode == 1 and "clean" not in p.stdout


# ---- reviewer C-764: a spaced-out domain, a line separator in a name, exact email matching, stated limits ----------------


@pytest.mark.parametrize("name", [
    "someone ＠ mail ． example ． invalid", "someone @ mail . example . invalid", "someone@mail . example",
    "someone @mail .invalid", "someone @ mail . invalid"])
def test_a_domain_spaced_around_its_dots_is_a_finding(name):
    assert fields(line(an=name)) == [("author name", "is an email address")]


@pytest.mark.parametrize("name", ["Dev @ Acme Corp", "Dev @ Acme", "Anna Smith . Jr", "Dr . Example", "@ handle", "Team @ Work, Inc."])
def test_ordinary_names_with_spaces_and_dots_still_pass(name):
    assert cci.check(line(an=name, cn=name)) == []


@pytest.mark.parametrize("sep", [" ", " ", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"])
def test_a_line_separator_in_a_name_is_not_a_line_break(sep):
    log = line(an="Example" + sep + "Person") + "\n" + line(sha="e" * 40, cn="Other" + sep + "Name")
    assert cci.check(log) == []
    assert len(cci.parse_log(log)) == 2


def test_a_line_separator_in_a_name_does_not_hide_a_finding():
    assert fields(line(an="x " + BAD_ADDR)) == [("author name", "is an email address")]


def test_windows_line_endings_are_accepted():
    assert len(cci.parse_log(line() + "\r\n" + line(sha="d" * 40) + "\r\n")) == 2
    assert cci.check(line() + "\r\n" + line(sha="d" * 40) + "\r\n") == []     # the carriage return is not part of the email


def test_the_cli_survives_a_line_separator_in_a_name(repo):
    p = _run(repo, "--stdin", stdin=line(an="Example Person"))
    assert p.returncode == 0 and "checked 1 commit)" in p.stdout


@pytest.mark.parametrize("email", [GOOD_EMAIL + " ", " " + GOOD_EMAIL, GOOD_EMAIL + "\t", "noreply@github.com "])
def test_a_padded_email_is_refused(email):
    assert fields(line(ae=email)) == [("author email", "is not an accepted no-reply form")]


def test_the_stated_limits_are_in_the_docstring():
    doc = cci.__doc__
    for phrase in ["--allow-domain D`` accepts EVERY local part", "checked 0 commits", "squash merge", "pull requests only",
                   "Enterprise Server", "spelled-out forms", "homoglyph", "is ACCEPTED by this check", "padding is a finding"]:
        assert phrase in doc, phrase


def test_the_documented_out_of_scope_spellings_really_pass():
    # a limit that the docstring states must stay true, or the docstring is wrong
    for name in ["someone at mail dot invalid", "someone AT mail DOT invalid", "someone.at.example.invalid", "plainusername"]:
        assert cci.check(line(an=name)) == [], name
    assert cci.check(line(an=BAD_ADDR.split("@")[0]), allow_domains=[]) == []
    assert cci.check(line(ae="anyone@corp.example.invalid"), allow_domains=["corp.example.invalid"]) == []


# ---- reviewer C-764 (delta): false positives and the trailer limit --------------------------------------------------------


@pytest.mark.parametrize("name", ["look [at] this", "look (at) this", "look {at} this", "at [at] home", "100%40 Club", "Ask &#64 me",
                                  "Look [AT] This.", "a [at] b"])
def test_prose_with_an_at_word_or_an_encoded_sign_is_not_an_address(name):
    assert cci.check(line(an=name)) == [], name


@pytest.mark.parametrize("name", [
    "someone[at]mail", "someone(at)mail", "someone{at}mail", "someone<at>mail", "someone[AT]mail", "someone [at] mail.example.invalid",
    "someone [at] mail [dot] example", "someone ( at ) mail . example", "someone%40mail", "someone&#64;mail", "someone&#x40;mail",
    "someone&commat;mail"])
def test_a_bracketed_or_encoded_at_between_words_is_still_a_finding(name):
    assert fields(line(an=name)) == [("author name", "is an email address")], name


@pytest.mark.parametrize("name", ["C@rl", "a@b", "J.R@Smith", "user@HOSTNAME"])
def test_the_documented_false_positives_stay_findings(name):
    assert fields(line(an=name)) == [("author name", "is an email address")]
    assert "C@rl" in cci.__doc__ and "false positives" in cci.__doc__


def test_the_trailer_limit_is_stated_in_the_docstring_and_the_job():
    assert "Co-authored-by" in cci.__doc__ and "ACCEPTED" in cci.__doc__
    ci = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Co-authored-by or Signed-off-by trailer is ACCEPTED" in ci


def test_a_trailer_in_the_body_is_not_read(repo):
    _git(repo, "update-ref", "refs/remotes/origin/main", "base")
    (Path(repo) / "f.txt").write_text("trailer")
    _git(repo, "add", "f.txt")
    ident = {"GIT_AUTHOR_NAME": GOOD_NAME, "GIT_AUTHOR_EMAIL": GOOD_EMAIL, "GIT_COMMITTER_NAME": GOOD_NAME, "GIT_COMMITTER_EMAIL": GOOD_EMAIL}
    _git(repo, "commit", "-q", "-m", "subject\n\nCo-authored-by: Someone <" + BAD_ADDR + ">", env=ident)
    p = _run(repo)
    assert p.returncode == 0 and "checked 1 commit)" in p.stdout        # the stated limit: a trailer address is accepted


# ---- reviewer C-788: dots that NFKC does not fold, a range of zero commits ---------------------------------------------


@pytest.mark.parametrize("dot", ["\u3002", "\uff61", "\ufe12", "\uff0e", "\u2024"])
def test_a_domain_with_an_ideographic_or_halfwidth_full_stop_is_a_finding(dot):
    assert fields(line(an=f"someone @ mail{dot}example{dot}invalid")) == [("author name", "is an email address")]
    assert fields(line(an=f"someone @ example{dot}invalid")) == [("author name", "is an email address")]
    assert fields(line(an=f"someone @ mail {dot} invalid")) == [("author name", "is an email address")]


def test_the_ideographic_full_stop_in_a_normal_name_is_not_a_finding():
    assert cci.check(line(an="\u674e\u96f7\u3002 Smith", cn="Example \uff61 Person")) == []


def test_the_dot_table_covers_both_characters():
    assert cci._DOTS == {0x3002: ".", 0xFF61: "."}


def test_require_commits_makes_a_range_of_zero_commits_exit_2(repo):
    p = _run(repo, "--require-commits", "--range", "main..main")
    assert p.returncode == 2 and "no commits" in p.stderr and "clean" not in p.stdout
    assert _run(repo, "--range", "main..main").returncode == 0                      # without the flag: still a pass with a count


def test_require_commits_is_satisfied_by_one_commit(repo):
    assert _run(repo, "--require-commits", "--stdin", stdin=line()).returncode == 0
    assert _run(repo, "--require-commits", "--stdin", stdin="").returncode == 2
    assert _run(repo, "--require-commits", "--stdin", stdin="\n\n").returncode == 2


def test_require_commits_still_reports_findings_with_exit_1(repo):
    assert _run(repo, "--require-commits", "--stdin", stdin=line(an=BAD_ADDR)).returncode == 1


def test_the_docstring_states_the_flag():
    assert "--require-commits" in cci.__doc__
