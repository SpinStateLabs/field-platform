"""`GET /clauses`, `sentinel clauses` and `sentinel score`: pinned (scout P-3, tests only, no source change).

Before: nothing in this suite named `clauses` or the `score` command, so the clause registry route, the CLI formatting and
the S2 scorecard command's exit codes (0 gates pass, 3 gates fail, 1 /health not 200) and output files were unpinned.
`score` builds real `httpx.Client`s, so the tests replace `cli.httpx.Client` / `cli.httpx.get` with the in-process stack's
TestClients (no network). `--ledger-down-cmd` is only ever a stub that records its call: no real command is run."""

from __future__ import annotations

import json
import subprocess
import time

import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli as cli_mod
from field_core.conformance import CLAUSES
from conformance_sentinel.mode import SentinelMode
from conformance_sentinel.seeded import build_corpus, provision
from tests.conftest import Stack

SENTINEL_URL, REGISTRY_URL, DELEGATION_URL = "http://sentinel.test", "http://registry.test", "http://delegation.test"


@pytest.fixture()
def stack(tmp_path):
    s = Stack(tmp_path)
    s.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY        # the served default the S2 suite measures
    return s


@pytest.fixture()
def wired(stack, tmp_path, monkeypatch):
    """Point the CLI's clients at the in-process stack."""
    monkeypatch.setenv("FIELD_SENTINEL_URL", SENTINEL_URL)
    monkeypatch.setenv("FIELD_REGISTRY_URL", REGISTRY_URL)
    monkeypatch.setenv("FIELD_DELEGATION_URL", DELEGATION_URL)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    by_url = {SENTINEL_URL: stack.sentinel, REGISTRY_URL: stack.registry, DELEGATION_URL: stack.delegation}
    monkeypatch.setattr(cli_mod.httpx, "Client", lambda base_url=None, **kw: by_url[base_url])
    monkeypatch.setattr(cli_mod.httpx, "get", lambda url, **kw: stack.sentinel.get(url.replace(SENTINEL_URL, "")))
    monkeypatch.setattr(time, "sleep", lambda s: None)               # the expired-token fixture's real wait is not the subject
    return stack


# -- GET /clauses -------------------------------------------------------------------------------------------------


def test_get_clauses_is_exactly_the_engine_registry(stack):
    r = stack.sentinel.get("/clauses")
    assert r.status_code == 200 and r.json() == CLAUSES and len(CLAUSES) > 5


def test_get_clauses_needs_the_perimeter_secret_when_one_is_set(stack, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-shared-secret-0000")
    assert stack.sentinel.get("/clauses").status_code == 401
    assert stack.sentinel.get("/clauses", headers={"x-field-auth": "wrong"}).status_code == 401
    assert stack.sentinel.get("/clauses", headers={"x-field-auth": "synthetic-shared-secret-0000"}).json() == CLAUSES


def test_every_clause_a_seeded_verdict_cites_is_in_the_registry(stack, tmp_path):
    fixtures = provision(registry=stack.registry, delegation=stack.delegation, manifest_dir=tmp_path, wait=lambda s: None)
    cited = set()
    for seed in build_corpus():
        if seed.token_kind not in fixtures.tokens:
            continue
        r = stack.sentinel.post("/check", json={"agent_id": fixtures.agent_id, "action": seed.action,
                                                "token_id": fixtures.tokens[seed.token_kind]})
        if r.status_code != 200:
            continue
        body = r.json()
        # log-only (the stack default): the clause a violation WOULD have cited is in context.would_be
        for cid in (body.get("clause_id"), ((body.get("context") or {}).get("would_be") or {}).get("clause_id")):
            if cid:
                cited.add(cid)
    assert {"D.scope", "D.revoked"} <= cited, cited        # the scan is not blind (what this corpus cites in log-only)
    assert cited <= set(CLAUSES), cited - set(CLAUSES)


# -- sentinel clauses ---------------------------------------------------------------------------------------------


def test_the_clauses_command_prints_one_padded_line_per_clause(wired):
    r = CliRunner().invoke(cli_mod.app, ["clauses"])
    assert r.exit_code == 0, r.output
    lines = r.output.splitlines()
    assert len(lines) == len(CLAUSES)
    for line, (cid, text) in zip(lines, CLAUSES.items()):
        assert line == f"{cid:22s} {text}"


def test_the_clauses_command_against_a_refusal_prints_the_error_pairs_and_exits_0_today(wired, monkeypatch):
    """KNOWN LIMIT, reported not fixed: `clauses` never looks at the status code, so a 401 answer's JSON body is printed as
    if it were the registry and the exit code is 0. Pinned so a fix is a decision."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-shared-secret-0000")
    r = CliRunner().invoke(cli_mod.app, ["clauses"])
    assert r.exit_code == 0
    assert not any(cid in r.output for cid in CLAUSES)


# -- sentinel score -----------------------------------------------------------------------------------------------


def test_score_exits_0_when_the_gates_pass_and_writes_both_files(wired, tmp_path):
    out_json, out_md = tmp_path / "score.json", tmp_path / "score.md"
    r = CliRunner().invoke(cli_mod.app, ["score", "--out-json", str(out_json), "--out-md", str(out_md),
                                         "--manifest-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "gates: PASS" in r.output and "seeds run:" in r.output
    assert json.loads(out_json.read_text(encoding="utf-8"))            # valid JSON, non-empty
    assert out_md.read_text(encoding="utf-8").strip()


def test_score_without_ledger_down_cmd_skips_the_ledger_seeds_and_runs_no_command(wired, tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or subprocess.CompletedProcess(a, 0, "", ""))
    r = CliRunner().invoke(cli_mod.app, ["score", "--manifest-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "skipped:" in r.output                                      # the ledger-unreachable group is named as skipped
    assert not any(isinstance(a[0], str) and a[0] for a in ran)        # no shell command (git rev-parse is a list)


def test_score_invokes_the_ledger_down_cmd_only_when_supplied_and_only_through_the_stub(wired, tmp_path, monkeypatch):
    shell_calls = []
    real_run = subprocess.run

    def stub(cmd, *a, **kw):
        if isinstance(cmd, str):                                       # the --ledger-down-cmd call (shell=True)
            shell_calls.append((cmd, kw.get("shell")))
            wired.ledger_up = False                                    # what the real command would do to the stack
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", stub)
    r = CliRunner().invoke(cli_mod.app, ["score", "--ledger-down-cmd", "STUB-LEDGER-DOWN", "--manifest-dir", str(tmp_path)])
    assert r.exit_code in (0, 3), r.output
    assert shell_calls == [("STUB-LEDGER-DOWN", True)]


def test_score_exits_3_when_the_gates_fail(wired, tmp_path, monkeypatch):
    """A sentinel whose log-only verdicts carry no would-be decision catches nothing: the catch gate fails."""
    real_post = wired.sentinel.post

    class Allow:
        status_code = 200

        def __init__(self, r):
            j = r.json()
            self._j = {**j, "context": {**(j.get("context") or {}), "would_be": None}}   # nothing would have been caught

        def json(self):
            return self._j

    def post(url, **kw):
        r = real_post(url, **kw)
        return Allow(r) if url == "/check" and r.status_code == 200 else r

    monkeypatch.setattr(wired.sentinel, "post", post)
    r = CliRunner().invoke(cli_mod.app, ["score", "--manifest-dir", str(tmp_path)])
    assert r.exit_code == 3, r.output
    assert "gates: FAIL" in r.output


def test_score_exits_1_when_health_is_not_200(wired, tmp_path, monkeypatch):
    class Down:
        status_code = 503

        def json(self):
            return {}

    monkeypatch.setattr(wired.sentinel, "get", lambda url, **kw: Down())
    r = CliRunner().invoke(cli_mod.app, ["score", "--manifest-dir", str(tmp_path)])
    assert r.exit_code == 1
    assert "sentinel /health returned 503" in r.output


def test_score_refuses_a_non_log_only_estate_with_exit_1(wired, tmp_path):
    wired.sentinel.app.state.engine.mode = SentinelMode.ENFORCE
    r = CliRunner().invoke(cli_mod.app, ["score", "--manifest-dir", str(tmp_path)])
    assert r.exit_code == 1, r.output
    assert "measurement refused" in r.output and "log-only" in r.output
