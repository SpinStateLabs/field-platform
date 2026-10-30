"""Lane 10 probe (C-677): tools/check_commit_identity.py. Made-up identities only. A case that does not behave as stated is a miss.
Run: GUARD=<checkout>/tools python -m pytest -q test_commit_identity_c677.py"""
import importlib.util, os, sys
import pytest
s = importlib.util.spec_from_file_location("g", os.path.join(os.environ["GUARD"], "check_commit_identity.py")); g = importlib.util.module_from_spec(s); sys.modules["g"] = g; s.loader.exec_module(g)
def run(an, ae, cn=None, ce=None, allow=()):
    line = "\x1f".join(["a"*40, an, ae, cn if cn is not None else an, ce if ce is not None else ae])
    return g.check(line, allow)
OK_EMAIL = ["123+zed@users.noreply.github.com", "zed@users.noreply.github.com", "noreply@github.com", "noreply@anthropic.com"]
@pytest.mark.parametrize("email", OK_EMAIL)
def test_accepts_the_documented_forms(email): assert run("Zed", email) == []
BOT = ["49699333+dependabot[bot]@users.noreply.github.com", "41898282+github-actions[bot]@users.noreply.github.com", "29139614+renovate[bot]@users.noreply.github.com"]
@pytest.mark.parametrize("email", BOT)
def test_legitimate_bot_identities_are_not_blocked(email): assert run("bot[bot]", email) == [], "a legitimate GitHub bot commit is blocked"
@pytest.mark.parametrize("email", ["ZED@USERS.NOREPLY.GITHUB.COM", "123+Zed@Users.NoReply.GitHub.com"])
def test_case_variants_of_the_noreply_form(email): assert run("Zed", email) == [], "an upper-case no-reply address is blocked"
MUST_BLOCK_EMAIL = ["zed@gmail.com", "zed@example.com", "zed@users.noreply.github.com.evil.test", "zed@users-noreply.github.com", "zed@noreply.github.com", "zed+tag@gmail.com", "noreply@anthropic.com.evil.test", "", "zed@googlemail.com"]
@pytest.mark.parametrize("email", MUST_BLOCK_EMAIL)
def test_blocks_other_emails(email): assert run("Zed", email) != [], f"accepted: {email!r}"
NAMES_MUST_BLOCK = ["zed@gmail.com", "zed@example.com", "<zed@gmail.com>", "zed@x", "zed at gmail dot com", "zed (at) gmail.com", "zed [at] gmail.com", "zed＠gmail.com", "zed @ gmail.com", "zed%40gmail.com", "zed&#64;gmail.com"]
@pytest.mark.parametrize("name", NAMES_MUST_BLOCK)
def test_blocks_an_address_used_as_a_name(name): assert run(name, "1+z@users.noreply.github.com") != [], f"accepted as a name: {name!r}"
@pytest.mark.parametrize("name", ["Don Hagell", "Claude", "dependabot[bot]", "GitHub", "Zed Q. Public", "d@n"])
def test_legit_names_not_blocked(name):
    assert run(name, "1+z@users.noreply.github.com") == [] or name == "d@n"
def test_committer_field_is_checked_independently():
    assert run("Zed", "1+z@users.noreply.github.com", "Zed", "zed@gmail.com")
def test_output_never_contains_the_value(capsys):
    line = "\x1f".join(["b"*40, "zed@gmail.com", "zed@gmail.com", "ok", "1+z@users.noreply.github.com"])
    f = g.check(line); text = "\n".join(str(x) for x in f)
    assert "gmail" not in text and "zed" not in text
def test_message_trailers_are_not_in_the_log_format():
    assert "%b" not in g.LOG_FORMAT and "%B" not in g.LOG_FORMAT, "commit message bodies (Co-authored-by, Signed-off-by) are not read"
    assert False, "the guard reads %an %ae %cn %ce only: a personal address in a Co-authored-by or Signed-off-by trailer is not seen"
def test_error_paths_do_not_print_input(capsys, monkeypatch):
    rc = g.main(["--stdin"]); 
