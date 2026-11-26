"""S3-18: `$` also matches before a final newline, so AGENT_RE, _HASH and _SHA applied with .match accepted
'--agent "canary\n"', '--hash <hex>\n' and '--expect-build-sha <sha>\n'. fullmatch refuses them with the same messages."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import estate_kill_watcher as watcher  # noqa: E402
import estate_probe as probe  # noqa: E402


def _watch_args(agent):
    return NS(manifest=None, sentinel="./sentinel", max_age_s=None, agent=agent, base="http://x",
              kill_prefix="/", interval=1.0, timeout=1.0)


@pytest.mark.parametrize("agent", ["a\n", "canary\n", "\nca"])
def test_a_watcher_agent_with_a_newline_is_refused_with_the_documented_message(agent):
    with pytest.raises(watcher.Refused, match="--agent must be 1-128 characters"):
        watcher.settle(_watch_args(agent))


def test_a_plain_watcher_agent_is_still_accepted():
    sentinel, age = watcher.settle(_watch_args("canary-1.a_b"))
    assert sentinel.endswith("sentinel") and age is None


@pytest.mark.parametrize("h", ["0123456789abcdef\n", "a" * 64 + "\n"])
def test_a_continuity_hash_with_a_trailing_newline_exits_through_die(h, capsys):
    with pytest.raises(SystemExit) as exc:
        probe.cmd_continuity(None, NS(count=1, hash=h))
    assert exc.value.code == 2
    assert "--hash 16-64 lowercase hex chars" in capsys.readouterr().err


@pytest.mark.parametrize("sha", ["a" * 40 + "\n", "b" * 64 + "\n"])
def test_an_expected_build_sha_with_a_trailing_newline_exits_through_die(sha, capsys):
    with pytest.raises(SystemExit) as exc:
        probe.cmd_health(None, NS(only=None, expect_build_sha=sha))
    assert exc.value.code == 2
    assert "--expect-build-sha must be the full" in capsys.readouterr().err


def test_a_clean_hash_and_sha_still_pass_the_pattern():
    assert probe._HASH.fullmatch("0123456789abcdef") and probe._SHA.fullmatch("a" * 40)
