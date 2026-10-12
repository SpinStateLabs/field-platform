"""Adversarial tests on the evidence pack: every kind of tampering must be
caught, and verification must trust only the key the verifier supplies."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from field_core.signing import generate_keypair

from agent_incident_retro.engine import run_retro
from agent_incident_retro.evidence import build_pack, verify_pack
from agent_incident_retro.report import render_markdown
from agent_incident_retro.synth import generate

GEN_AT = "2026-10-11T00:00:00+00:00"


@pytest.fixture
def artifacts(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    result = run_retro([log], fmt="clf")
    priv, pub = generate_keypair()
    report = render_markdown(result, GEN_AT)
    pack = build_pack(result, report, GEN_AT, priv)
    return {"pack": pack, "pub": pub, "priv": priv, "report": report, "log": log}


def _ok(result):
    return result.ok, {c.name: c.ok for c in result.checks}


def test_clean_pack_verifies(artifacts):
    ok, checks = _ok(
        verify_pack(
            artifacts["pack"],
            artifacts["pub"],
            artifacts["report"].encode("utf-8"),
            {"synth.log": artifacts["log"].read_bytes()},
        )
    )
    assert ok, checks


def test_event_mutation_breaks_chain(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    pack["events"][1]["payload"]["verdict"] = "CLEAR"
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok
    assert not checks["hash chain"]


def test_finding_edit_breaks_binding(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    # edit a finding but leave its flagged event's digest alone
    pack["findings"][0]["client_ip"] = "10.0.0.1"
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok
    assert not checks["findings bound to events"]


def test_pack_signature_tamper_detected(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    pack["summary"]["requests_total"] = 1
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok
    assert not checks["pack signature"]


def test_resign_with_other_key_fails_pinned_fingerprint(artifacts):
    """An attacker edits the pack and re-signs with their own key. Verified
    against the real signer's public key, the fingerprint must not match."""
    result_priv, result_pub = generate_keypair()  # attacker key
    pack = copy.deepcopy(artifacts["pack"])
    pack["summary"]["requests_total"] = 1
    body = {k: v for k, v in pack.items() if k != "signature"}
    # re-sign body and swap in the attacker's advertised key
    import base64

    from field_core.signing import key_fingerprint, load_ed25519_private_key
    from agent_incident_retro.evidence import canonical

    pack["signer"]["public_key_pem"] = result_pub
    pack["signer"]["public_key_fingerprint"] = key_fingerprint(result_pub)
    body = {k: v for k, v in pack.items() if k != "signature"}
    pack["signature"] = base64.b64encode(load_ed25519_private_key(result_priv).sign(canonical(body))).decode()
    # the pack is internally consistent, but fails against the REAL signer key
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok
    assert not checks["signer fingerprint"]


def test_report_digest_mismatch_detected(artifacts):
    ok, checks = _ok(verify_pack(artifacts["pack"], artifacts["pub"], b"a different report"))
    assert not ok
    assert not checks["report digest"]


def test_source_line_tamper_detected(artifacts):
    data = artifacts["log"].read_bytes()
    lines = data.split(b"\n")
    # tamper a cited line: find the first flagged event's first evidence line
    flagged = next(e for e in artifacts["pack"]["events"] if e["event_type"] == "retro.session.flagged")
    n = flagged["payload"]["evidence_lines"][0]["line"]
    lines[n - 1] = lines[n - 1] + b" TAMPERED"
    ok, checks = _ok(verify_pack(artifacts["pack"], artifacts["pub"], sources={"synth.log": b"\n".join(lines)}))
    assert not ok
    assert not checks["cited source lines"]


def test_wrong_source_file_detected(artifacts):
    ok, checks = _ok(verify_pack(artifacts["pack"], artifacts["pub"], sources={"synth.log": b"totally different\n"}))
    assert not ok
    assert not checks["source file digests"]


def test_determinism_same_input_same_pack_bar_timestamp(tmp_path: Path):
    log = tmp_path / "s.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    priv, _ = generate_keypair()
    r1 = run_retro([log], fmt="clf")
    r2 = run_retro([log], fmt="clf")
    p1 = build_pack(r1, render_markdown(r1, GEN_AT), GEN_AT, priv)
    p2 = build_pack(r2, render_markdown(r2, GEN_AT), GEN_AT, priv)
    # same generated_at and key -> byte-identical pack (determinism)
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_malformed_event_shape_is_a_failed_check_not_a_crash(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    pack["events"][0] = {"not": "an event"}
    result = verify_pack(pack, artifacts["pub"])
    assert not result.ok  # did not raise


def test_head_truncation_detected(artifacts):
    """Drop the last event but leave chain.head pointing at it."""
    pack = copy.deepcopy(artifacts["pack"])
    pack["events"] = pack["events"][:-1]
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok and not checks["hash chain"]


def test_single_event_signature_tamper_detected(artifacts):
    """Swap one event's signature for another event's — chain still links,
    but that event's signature no longer matches its bytes."""
    pack = copy.deepcopy(artifacts["pack"])
    assert len(pack["events"]) >= 3
    pack["events"][1]["signature"], pack["events"][2]["signature"] = (
        pack["events"][2]["signature"],
        pack["events"][1]["signature"],
    )
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok and not checks["event signatures"]


def test_last_finding_edit_breaks_binding(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    assert len(pack["findings"]) >= 2
    pack["findings"][-1]["client_ip"] = "10.9.9.9"
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok and not checks["findings bound to events"]


def test_any_cited_line_tamper_detected(artifacts):
    """Every cited line is re-hashed, not just the first: tampering the LAST
    cited line of the LAST flagged event must still fail."""
    flagged = [e for e in artifacts["pack"]["events"] if e["event_type"] == "retro.session.flagged"]
    ref = flagged[-1]["payload"]["evidence_lines"][-1]
    data = artifacts["log"].read_bytes().split(b"\n")
    data[ref["line"] - 1] = data[ref["line"] - 1] + b" X"
    ok, checks = _ok(verify_pack(artifacts["pack"], artifacts["pub"], sources={"synth.log": b"\n".join(data)}))
    assert not ok and not checks["cited source lines"]


def test_inputs_bound_to_chain_edit_detected(artifacts):
    pack = copy.deepcopy(artifacts["pack"])
    pack["inputs"][0]["sha256"] = "0" * 64
    ok, checks = _ok(verify_pack(pack, artifacts["pub"]))
    assert not ok  # the first event's named input digest no longer matches
