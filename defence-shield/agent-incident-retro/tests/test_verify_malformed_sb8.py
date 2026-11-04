"""`retro verify` is the auditor-facing verifier: a malformed pack, a missing file or
truncated JSON must FAIL cleanly (exit 1, no traceback), never crash (scout S-B8)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from field_core.signing import generate_keypair
from typer.testing import CliRunner

from agent_incident_retro.cli import app
from agent_incident_retro.engine import run_retro
from agent_incident_retro.evidence import build_pack, verify_pack
from agent_incident_retro.report import render_markdown
from agent_incident_retro.synth import generate

GEN_AT = "2026-10-11T00:00:00+00:00"
runner = CliRunner()


@pytest.fixture
def art(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    result = run_retro([log], fmt="clf")
    priv, pub = generate_keypair()
    pack = build_pack(result, render_markdown(result, GEN_AT), GEN_AT, priv)
    pub_file = tmp_path / "p.pub"
    pub_file.write_text(pub, encoding="utf-8")
    return {"pack": pack, "pub": pub, "pub_file": pub_file, "dir": tmp_path}


def _mut(art, **changes):
    p = copy.deepcopy(art["pack"])
    p.update(changes)
    return p


@pytest.mark.parametrize("changes", [
    {"signer": "x"}, {"signer": [1]}, {"chain": "x"}, {"chain": 5},
    {"findings": [1]}, {"findings": "x"}, {"findings": {"a": 1}},
    {"inputs": [1]}, {"inputs": "x"}, {"events": "x"}, {"events": 5},
])
def test_a_malformed_part_is_a_failed_check_not_a_crash(art, changes):
    result = verify_pack(_mut(art, **changes), art["pub"])
    assert result.ok is False


@pytest.mark.parametrize("pack", [[], "x", 5, None])
def test_a_pack_that_is_not_an_object_fails(art, pack):
    assert verify_pack(pack, art["pub"]).ok is False


def test_the_clean_pack_still_verifies(art):
    assert verify_pack(art["pack"], art["pub"]).ok is True


def _run(art, content=None, pub=None, extra=()):
    pack_file = art["dir"] / "pack.json"
    if content is not None:
        pack_file.write_text(content, encoding="utf-8")
    return runner.invoke(app, ["verify", str(pack_file), "--pub", str(pub or art["pub_file"]), *extra])


@pytest.mark.parametrize("content", ['{"signer": "x"}', "[]", '{"findings":[1],"events":[]}', "null", '{"a":'])
def test_cli_verify_on_a_bad_pack_exits_1_without_a_traceback(art, content):
    r = _run(art, content)
    assert r.exit_code == 1, r.output
    assert not isinstance(r.exception, (AttributeError, TypeError, KeyError, json.JSONDecodeError))
    assert "FAILED" in r.output or "cannot" in r.output.lower()


def test_cli_verify_a_missing_pack_or_key_exits_1(art):
    r = runner.invoke(app, ["verify", str(art["dir"] / "nope.json"), "--pub", str(art["pub_file"])])
    assert r.exit_code == 1 and not isinstance(r.exception, FileNotFoundError)
    r = _run(art, json.dumps(art["pack"]), pub=art["dir"] / "missing.pub")
    assert r.exit_code == 1 and not isinstance(r.exception, FileNotFoundError)


def test_cli_verify_a_clean_pack_still_exits_0(art):
    assert _run(art, json.dumps(art["pack"])).exit_code == 0
