"""renew_token signing pins (BACKLOG B-14, reviewer C-215 F-C215-1/-2/-3 on PR 106).

The integration file (test_renew_token.py) runs the tool as a subprocess against the real
services, where field_core is installed and every append succeeds or fails once; so the
repo-path fallback, the "loaded once" rule, a second dropped append and the no-leak rule of
the "caller signing unavailable" message were never exercised. These tests drive the
Renewal.ledger / caller_signer / add_repo_field_core code directly, in process, with a fake
Api, so each surviving mutant of C-215 goes red:

  A08 find_spec test inverted, A09 always add, A10 and G1426 the `not in sys.path` guard
  inverted, A11 isdir inverted, A12 insert(0) for append, A13 wrong root, G1423
  `is not False`, G1427 append removed      -> test_repo_path_fallback_*
  A01 the signer reloaded on every append   -> test_the_signer_is_loaded_once_*
  A25 dropped_ledger_appends fixed at 1     -> test_two_failed_appends_*
  A15 the exception text printed            -> test_an_unavailable_signer_prints_the_type_name_only
  A32 strip removed on the key variable     -> test_a_whitespace_only_caller_key_counts_as_not_set

No key, no PEM and no real service: the "signer" is a sentinel object.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import renew_token  # noqa: E402

field_core_clients = pytest.importorskip("field_core.clients")

ID_ENV, KEY_ENV = renew_token.CALLER_ID_ENV, renew_token.CALLER_KEY_ENV


class FakeApi:
    """Answers every call from a script of (status, body); records the bodies it was sent."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, str, object]] = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        return self.answers.pop(0) if self.answers else (201, {"id": "x"})


def renewal(api: FakeApi, secret: str | None = "s3cret-for-the-test-only") -> renew_token.Renewal:
    """A Renewal with only what ledger(), caller_signer() and add_repo_field_core() read."""
    r = object.__new__(renew_token.Renewal)
    r.api = api
    r.a = argparse.Namespace(agent="agent-under-test")
    r.secret = secret
    return r


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ID_ENV, raising=False)
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))  # every test gets its own copy to append to


# ------------------------------------------------------------ F-C215-1: the repo-path fallback

def _fake_checkout(tmp_path: Path, with_src: bool = True) -> tuple[Path, Path]:
    tool = tmp_path / "checkout" / "tools" / "renew_token.py"
    tool.parent.mkdir(parents=True)
    tool.write_text("# stand-in for the tool file\n", encoding="utf-8")
    src = tmp_path / "checkout" / "packages" / "field-core" / "src"
    if with_src:
        src.mkdir(parents=True)
    return tool, src


def test_repo_path_fallback_appends_this_checkouts_field_core_src_once_and_last(tmp_path, monkeypatch):
    """No field_core installed, the checkout has packages/field-core/src: that path is APPENDED (an installed
    copy, earlier on sys.path, always wins) exactly once, and it is the checkout beside tools/, not elsewhere."""
    tool, src = _fake_checkout(tmp_path)
    monkeypatch.setattr(renew_token, "__file__", str(tool))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    sys.path.append(str(tmp_path / "somewhere-else"))  # a known last entry before the call
    before = list(sys.path)

    renew_token.Renewal.add_repo_field_core()

    assert sys.path[:-1] == before, "the fallback must not move or remove any existing entry (append, never insert)"
    assert sys.path[-1] == str(src), sys.path[-1]
    assert sys.path.count(str(src)) == 1

    renew_token.Renewal.add_repo_field_core()  # a second call does not add it again
    assert sys.path.count(str(src)) == 1 and sys.path[-1] == str(src)


def test_repo_path_fallback_does_nothing_when_field_core_is_installed(tmp_path, monkeypatch):
    tool, src = _fake_checkout(tmp_path)
    monkeypatch.setattr(renew_token, "__file__", str(tool))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())  # "installed"
    before = list(sys.path)
    renew_token.Renewal.add_repo_field_core()
    assert sys.path == before
    assert str(src) not in sys.path


def test_repo_path_fallback_does_nothing_when_the_checkout_has_no_field_core_src(tmp_path, monkeypatch):
    tool, src = _fake_checkout(tmp_path, with_src=False)
    monkeypatch.setattr(renew_token, "__file__", str(tool))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    before = list(sys.path)
    renew_token.Renewal.add_repo_field_core()
    assert sys.path == before
    assert all(not p.endswith(os.path.join("field-core", "src")) or p in before for p in sys.path)


def test_repo_path_fallback_is_asked_before_the_signer_import(monkeypatch, capsys):
    """caller_signer() calls add_repo_field_core() when both variables are set (the import that follows
    needs it on a host without an installed field_core)."""
    monkeypatch.setenv(ID_ENV, "caller-a")
    monkeypatch.setenv(KEY_ENV, "/nonexistent/for-the-test.pem")
    asked = []
    monkeypatch.setattr(renew_token.Renewal, "add_repo_field_core", staticmethod(lambda: asked.append(1)))
    monkeypatch.setattr(field_core_clients.CallerSigner, "from_env", classmethod(lambda cls: object()))
    r = renewal(FakeApi())
    assert r.caller_signer() is not None
    assert asked == [1]
