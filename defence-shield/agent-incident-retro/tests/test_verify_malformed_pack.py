"""S8-29: `retro verify` is what a third party runs on an UNTRUSTED pack. An odd or hostile pack must be
a failed, named check (and exit 1 from the CLI), never a traceback or a KeyError."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from field_core.signing import generate_keypair

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
    report = render_markdown(result, GEN_AT)
    return {"pack": build_pack(result, report, GEN_AT, priv), "pub": pub, "log": log, "report": report}


def _verify(art, mutate=None, sources=True):
    pack = copy.deepcopy(art["pack"])
    if mutate:
        pack = mutate(pack)
    src = {"synth.log": art["log"].read_bytes()} if sources else None
    return verify_pack(pack, art["pub"], art["report"].encode("utf-8"), src)


def _failed(result):
    return {c.name for c in result.checks if not c.ok}


def test_the_clean_pack_still_verifies_with_the_same_checks(art):
    result = _verify(art)
    assert result.ok
    names = [c.name for c in result.checks]
    assert not any("shape" in n for n in names)           # no new check on a good pack


@pytest.mark.parametrize("bad", [[], None, "x", 7, ["a"]])
def test_a_pack_that_is_not_an_object_is_a_failed_check(art, bad):
    result = verify_pack(bad, art["pub"])
    assert result.ok is False and "pack shape" in _failed(result)


@pytest.mark.parametrize("field,value", [("signer", "x"), ("signer", []), ("signer", None), ("chain", []),
                                         ("chain", "x"), ("chain", 3)])
def test_a_non_object_signer_or_chain_fails_a_named_check(art, field, value):
    result = _verify(art, lambda p: {**p, field: value})
    assert result.ok is False
    assert _failed(result) & {"signer fingerprint", "hash chain"}


@pytest.mark.parametrize("events", ["x", {"a": 1}, 5, None])
def test_events_that_are_not_a_list_fail_the_events_check(art, events):
    result = _verify(art, lambda p: {**p, "events": events})
    assert "events parse" in _failed(result)


@pytest.mark.parametrize("findings", ["x", {"a": 1}, [1, "x", None], [[]]])
def test_findings_that_are_not_objects_fail_the_findings_shape_check(art, findings):
    result = _verify(art, lambda p: {**p, "findings": findings})
    assert result.ok is False and "findings shape" in _failed(result)


@pytest.mark.parametrize("request_entry", [{}, {"ref": {}}, {"ref": {"sha256": "x"}}, {"ref": "x"}, "x", None,
                                           {"ref": {"input": "a", "line": "1", "sha256": "x"}}])
def test_a_request_without_a_usable_ref_fails_the_findings_shape_check(art, request_entry):
    def mutate(p):
        p["findings"][0]["requests"] = [request_entry]
        return p
    result = _verify(art, mutate)
    assert result.ok is False and "findings shape" in _failed(result)


def test_a_findings_requests_that_is_not_a_list_fails_the_shape_check(art):
    def mutate(p):
        p["findings"][0]["requests"] = {"a": 1}
        return p
    assert "findings shape" in _failed(_verify(art, mutate))


@pytest.mark.parametrize("inputs", [[{}], [{"label": "a"}], [{"sha256": "x"}], ["x"], "x", {"a": 1}, [None],
                                    [{"label": 1, "sha256": "x"}]])
def test_inputs_without_label_and_sha256_fail_the_inputs_shape_check(art, inputs):
    result = _verify(art, lambda p: {**p, "inputs": inputs})
    assert result.ok is False and "inputs shape" in _failed(result)


@pytest.mark.parametrize("line", [{}, {"input": "synth.log"}, {"input": "synth.log", "line": 1},
                                  {"input": ["x"], "line": 1, "sha256": "x"}, "x", None, 5,
                                  {"input": "synth.log", "line": True, "sha256": "x"}])
def test_an_evidence_line_without_input_line_and_sha256_fails_its_check(art, line):
    def mutate(p):
        for e in p["events"]:
            if e["event_type"] == "retro.session.flagged":
                e["payload"]["evidence_lines"] = [line]
        return p
    result = _verify(art, mutate)
    assert result.ok is False and "evidence lines shape" in _failed(result)


def test_evidence_lines_that_is_not_a_list_fails_its_check(art):
    def mutate(p):
        for e in p["events"]:
            if e["event_type"] == "retro.session.flagged":
                e["payload"]["evidence_lines"] = "x"
        return p
    assert "evidence lines shape" in _failed(_verify(art, mutate))


@pytest.mark.parametrize("raw", [5, [1], {"a": 1}, True])
def test_a_request_whose_raw_is_not_a_string_does_not_raise(art, raw):
    def mutate(p):
        for e in p["events"]:
            if e["event_type"] == "retro.session.flagged":
                e["payload"].setdefault("requests", [])
        for f in p["findings"]:
            for req in f.get("requests", []):
                req["raw"] = raw
        return p
    result = _verify(art, mutate)
    assert result.ok is False


# -- the CLI: unreadable inputs are one line and exit 1 ---------------------------------------------


def _run(tmp_path: Path, art, pack_bytes=None, pub=None, extra=()):
    pack_path = tmp_path / "pack.json"
    if pack_bytes is not None:
        pack_path.write_bytes(pack_bytes)
    pub_path = tmp_path / "air.pub"
    pub_path.write_text(art["pub"] if pub is None else pub, encoding="utf-8")
    return runner.invoke(app, ["verify", str(pack_path), "--pub", str(pub_path), *extra])


def test_cli_missing_pack_is_one_line_exit_1(tmp_path, art):
    r = _run(tmp_path, art)
    assert r.exit_code == 1 and "error: could not read the pack: FileNotFoundError" in r.output
    assert "Traceback" not in r.output


def test_cli_directory_as_the_pack(tmp_path, art):
    d = tmp_path / "dir"
    d.mkdir()
    r = runner.invoke(app, ["verify", str(d), "--pub", str(tmp_path / "p")])
    assert r.exit_code == 1 and "could not read the pack" in r.output


@pytest.mark.parametrize("payload", [b"\xff\xfe\x00\x01", b"{not json", b"", b"[" * 200000],
                         ids=["binary", "not-json", "empty", "nested-too-deep"])
def test_cli_binary_or_non_json_pack(tmp_path, art, payload):
    r = _run(tmp_path, art, payload)
    assert r.exit_code == 1 and "could not read the pack" in r.output and "Traceback" not in r.output


def test_cli_pack_that_loads_but_is_too_deep_to_verify_is_one_line_exit_1(tmp_path, art):
    # json.loads accepts this depth (3.14.2: 16000), canonical() then recurses past the limit: the same one line as a pack json cannot load
    deep = "[" * 16000 + "]" * 16000
    pack_path = tmp_path / "pack.json"
    pack_path.write_text('{"signer": ' + deep + "}", encoding="utf-8")
    pub_path = tmp_path / "air.pub"
    pub_path.write_text(art["pub"], encoding="utf-8")
    r = runner.invoke(app, ["verify", str(pack_path), "--pub", str(pub_path)])
    assert not isinstance(r.exception, RecursionError)
    assert r.exit_code == 1 and "error: could not read the pack: RecursionError" in r.output


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"x"', b"5"])
def test_cli_non_object_json_pack_fails_verification_cleanly(tmp_path, art, payload):
    r = _run(tmp_path, art, payload)
    assert r.exit_code == 1 and "[FAIL] pack shape" in r.output and "VERIFICATION FAILED" in r.output


def test_cli_unreadable_pub_report_and_sources(tmp_path, art):
    good = tmp_path / "pack.json"
    good.write_text(json.dumps(art["pack"]), encoding="utf-8")
    r = runner.invoke(app, ["verify", str(good), "--pub", str(tmp_path / "nope.pub")])
    assert r.exit_code == 1 and "could not read --pub" in r.output
    (tmp_path / "air.pub").write_text(art["pub"], encoding="utf-8")
    r = runner.invoke(app, ["verify", str(good), "--pub", str(tmp_path / "air.pub"),
                            "--report", str(tmp_path / "missing.md")])
    assert r.exit_code == 1 and "could not read --report" in r.output
    r = runner.invoke(app, ["verify", str(good), "--pub", str(tmp_path / "air.pub"),
                            "--sources", str(tmp_path / "missing.log")])
    assert r.exit_code == 1 and "could not read --sources" in r.output
    assert "Traceback" not in r.output
