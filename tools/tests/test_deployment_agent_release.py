"""Release-record verifier skeleton: exact 40-hex SHA, a signature via an INJECTED verifier, no crypto here."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent.actions import Action, ActionKind  # noqa: E402
from deployment_agent.refuse import refuse  # noqa: E402
from deployment_agent.release import (  # noqa: E402
    REQUIRED_STAGES, ReleaseRecordError, canonical_payload, verify_release,
)

SHA = "0123456789abcdef0123456789abcdef01234567"
H = "ab" * 32


def record(**over):
    r = {
        "sha": SHA,
        "image_digests": {"estate": "sha256:" + H},
        "stage_results": {s: H for s in REQUIRED_STAGES},
        "gate_pass_digest": H,
        "signature": "sig-ok",
    }
    r.update(over)
    return r


def accept_ok(payload: bytes, signature: str) -> bool:
    return signature.startswith("sig-ok")


def test_a_well_formed_signed_record_for_the_exact_sha_verifies():
    v = verify_release(record(), SHA, accept_ok)
    assert v.sha == SHA and v.adr_override is None


def test_the_verifier_is_handed_the_canonical_payload_without_the_signature():
    seen = {}

    def spy(payload, signature):
        seen["payload"], seen["sig"] = payload, signature
        return True
    verify_release(record(), SHA, spy)
    assert seen["sig"] == "sig-ok" and b"signature" not in seen["payload"] and SHA.encode() in seen["payload"]
    assert seen["payload"] == canonical_payload(record())


@pytest.mark.parametrize("short", [SHA[:7], SHA[:12], SHA[:39], SHA + "0", SHA.upper(), "", "HEAD", "main"])
def test_a_short_or_malformed_sha_is_refused_on_either_side(short):
    with pytest.raises(ReleaseRecordError):
        verify_release(record(sha=short), SHA, accept_ok)
    with pytest.raises(ReleaseRecordError):
        verify_release(record(), short, accept_ok)
    with pytest.raises(ReleaseRecordError):
        verify_release(record(sha=short), short, accept_ok)  # even when they agree


def test_a_record_for_another_sha_is_refused():
    with pytest.raises(ReleaseRecordError, match="different SHA"):
        verify_release(record(sha="f" * 40), SHA, accept_ok)


@pytest.mark.parametrize("sig", [None, "", "   ", 7, ["sig-ok"]])
def test_a_missing_or_malformed_signature_is_refused(sig):
    r = record()
    r["signature"] = sig
    with pytest.raises(ReleaseRecordError):
        verify_release(r, SHA, accept_ok)
    del r["signature"]
    with pytest.raises(ReleaseRecordError):
        verify_release(r, SHA, accept_ok)


def test_a_signature_the_injected_verifier_rejects_is_refused():
    with pytest.raises(ReleaseRecordError, match="not accepted"):
        verify_release(record(signature="forged"), SHA, accept_ok)


def test_a_verifier_that_raises_never_counts_as_a_pass():
    def boom(payload, signature):
        raise RuntimeError("x")
    with pytest.raises(ReleaseRecordError):
        verify_release(record(), SHA, boom)


def test_a_verifier_must_return_exactly_true():
    with pytest.raises(ReleaseRecordError):
        verify_release(record(), SHA, lambda p, s: "yes")


def test_the_default_verifier_fails_closed_with_a_pointer_to_the_adr():
    with pytest.raises(NotImplementedError, match="ADR-0079"):
        verify_release(record(), SHA)


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("image_digests"),
    lambda r: r.update(image_digests={}),
    lambda r: r.update(image_digests={"estate": "latest"}),
    lambda r: r.update(image_digests={"estate": "sha256:abc"}),
    lambda r: r["stage_results"].pop("redteam"),
    lambda r: r["stage_results"].update(evals="nothex"),
    lambda r: r.pop("stage_results"),
    lambda r: r.update(gate_pass_digest="short"),
    lambda r: r.pop("gate_pass_digest"),
])
def test_malformed_record_bodies_are_refused(mutate):
    r = copy.deepcopy(record())
    mutate(r)
    with pytest.raises(ReleaseRecordError):
        verify_release(r, SHA, accept_ok)


def test_an_adr_override_needs_a_human_signed_approval_that_the_verifier_accepts():
    with pytest.raises(ReleaseRecordError, match="human-signed"):
        verify_release(record(adr_override="ADR-0099"), SHA, accept_ok)
    approval = {"approver": "Don Hagell", "signature": "sig-ok-approval"}
    v = verify_release(record(adr_override="ADR-0099", override_approval=approval), SHA, accept_ok)
    assert v.adr_override == "ADR-0099" and v.override_approver == "Don Hagell"
    with pytest.raises(ReleaseRecordError, match="override approval signature"):
        verify_release(record(adr_override="ADR-0099", override_approval={"approver": "x", "signature": "forged"}),
                       SHA, accept_ok)


def test_only_a_verified_release_unlocks_the_deploy_rule_and_only_for_that_sha():
    assert refuse(Action(ActionKind.RUN_ESTATE_DEPLOY, sha=SHA)).startswith("R05")
    v = verify_release(record(), SHA, accept_ok)
    assert refuse(Action(ActionKind.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=v.sha,
                              estate_killed=False, journal_pending=False)) is None
    assert refuse(Action(ActionKind.RUN_ESTATE_DEPLOY, sha="e" * 40, verified_release_sha=v.sha)).startswith("R05")
