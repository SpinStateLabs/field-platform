"""S5-22: a minted token is on disk before anything else can fail.

main() used to collect tokens in memory and write the file once after the loop; probe() and the final ledger
verify call .json() on unguarded transport calls, so one httpx error, non-JSON answer or KeyError aborted main with a
traceback BEFORE the write: the tokens existed on the estate, none was saved, and the next run minted more.
(A corrupt tokens file and a junk TTL are the separate scout S-A6 change.)"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import provision_ssl_agents as psa  # noqa: E402

AGENT_1, AGENT_2 = list(psa.AGENTS)


class Engine:
    def __init__(self, ids):
        self.ids = ids

    def provision(self, **kw):
        agent = Path(kw["manifest_path"]).stem
        return NS(ok=True, steps=[], token_id=self.ids[agent], scope=["x"])


class Http:
    def __init__(self, fail=False):
        self.fail = fail

    def get(self, url, **kw):
        if self.fail:
            raise httpx.ConnectError("down")
        return NS(json=lambda: {"ok": True})


@pytest.fixture()
def run(tmp_path, monkeypatch):
    tokens = tmp_path / "keys" / "tokens.json"
    monkeypatch.setattr(psa, "PROXY", "http://estate.invalid")
    monkeypatch.setattr(psa, "TOKENS_FILE", tokens)
    monkeypatch.setattr(psa, "health", lambda: None)
    monkeypatch.setattr(psa, "operator_pair", lambda *a: None)
    monkeypatch.setattr(psa, "client", lambda pair: None)
    monkeypatch.setattr(psa, "build_engine", lambda c=None: Engine({AGENT_1: "tok-1", AGENT_2: "tok-2"}))

    def go(probe, http=None):
        monkeypatch.setattr(psa, "probe", probe)
        monkeypatch.setattr(psa, "H", http or Http())
        return psa.main([]), tokens
    return go


def _ok(agent_id, meta, scope, token_id):
    return []


def test_a_probe_that_raises_for_the_second_agent_leaves_both_tokens_on_disk_and_exits_1(run, capsys):
    def probe(agent_id, meta, scope, token_id):
        if agent_id == AGENT_2:
            raise httpx.ConnectError("down")
        return []
    code, tokens = run(probe)
    assert code == 1
    assert json.loads(tokens.read_text(encoding="utf-8")) == {AGENT_1: "tok-1", AGENT_2: "tok-2"}
    out = capsys.readouterr().out
    assert f"FAILED {AGENT_2}: ConnectError" in out and "down" not in out


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("t"), ValueError("not json"), KeyError("k")])
def test_every_probe_failure_is_one_agents_failure_and_the_run_continues(run, exc, capsys):
    seen = []

    def probe(agent_id, meta, scope, token_id):
        seen.append(agent_id)
        raise exc
    code, tokens = run(probe)
    assert code == 1 and seen == [AGENT_1, AGENT_2]
    assert set(json.loads(tokens.read_text(encoding="utf-8"))) == {AGENT_1, AGENT_2}


def test_the_token_is_saved_before_the_probe_runs(run):
    def probe(agent_id, meta, scope, token_id):
        assert agent_id in json.loads(psa.TOKENS_FILE.read_text(encoding="utf-8"))
        return []
    assert run(probe)[0] == 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_the_tokens_file_is_0600_and_no_temp_file_is_left(run):
    code, tokens = run(_ok)
    assert code == 0 and (tokens.stat().st_mode & 0o777) == 0o600
    assert [p.name for p in tokens.parent.iterdir()] == ["tokens.json"]


def test_a_ledger_verify_failure_is_a_failure_not_a_traceback(run, capsys):
    code, tokens = run(_ok, http=Http(fail=True))
    assert code == 1 and "ledger verify: unavailable (ConnectError)" in capsys.readouterr().out
    assert set(json.loads(tokens.read_text(encoding="utf-8"))) == {AGENT_1, AGENT_2}


def test_a_manifest_name_mismatch_is_a_refusal_not_an_assert(monkeypatch):
    monkeypatch.setattr(psa, "manifest", lambda a: {"agent": {"name": "other"}, "identity": {"principal": "p"}})
    with pytest.raises(ValueError, match="manifest name mismatch"):
        psa.provision_agent(AGENT_1, psa.AGENTS[AGENT_1], engine=object())
