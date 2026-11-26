"""The standard-library tools spell the registry's agent-id rule themselves: they stay equal to ``field_core.ids``.
The estate kill watcher treats an estate's 422 for its agent id as a halt."""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

from field_core.ids import REGISTRY_ID_MAX_LENGTH, REGISTRY_ID_RE, registry_id_ok

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import estate_kill_watcher as watcher  # noqa: E402
import renew_token  # noqa: E402

SAMPLES = ["a", "0", "invoicing-agent", "a..b_c-", "a" * 128, "a" * 129, "", "A", "-a", ".a", "_a", "a b", "a/b",
           "a?b", "a#b", "a%2Fb", "a" + chr(10), "a" + chr(0x202E), chr(0xE9)]


@pytest.mark.parametrize("value", SAMPLES)
def test_the_watcher_accepts_exactly_the_rule(value):
    assert (watcher.AGENT_RE.fullmatch(value) is not None) is registry_id_ok(value)


def test_the_renewal_tool_spells_the_same_pattern():
    assert renew_token.AGENT_ID.pattern == REGISTRY_ID_RE.pattern
    assert REGISTRY_ID_MAX_LENGTH == 128


def _refusing(code):
    class Opener:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, code, "refused", None, None)

    return Opener()


def test_a_422_for_the_agent_id_creates_the_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "_OPENER", _refusing(422))
    sentinel = tmp_path / "KILL"
    code = watcher.main(["--agent", "a1", "--base", "http://127.0.0.1:1", "--sentinel", str(sentinel), "--once"])
    assert code == 0 and sentinel.exists() and (tmp_path / "KILL.alive").exists()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_other_refusals_stay_no_answer(tmp_path, monkeypatch, status):
    monkeypatch.setattr(watcher, "_OPENER", _refusing(status))
    sentinel = tmp_path / "KILL"
    code = watcher.main(["--agent", "a1", "--base", "http://127.0.0.1:1", "--sentinel", str(sentinel), "--once"])
    assert code == 3 and not sentinel.exists()


@pytest.mark.parametrize("agent", ["Upper-Case", "-a", "a b", "a" * 129])
def test_an_agent_id_outside_the_rule_is_refused_at_start(tmp_path, agent):
    argv = ["--agent=" + agent, "--base", "http://127.0.0.1:1", "--sentinel", str(tmp_path / "KILL"), "--once"]
    assert watcher.main(argv) == 2
    assert not (tmp_path / "KILL").exists()
