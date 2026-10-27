"""Phase G Stage 0 follow-up: ``operator_on_behalf_of`` is a RESERVED ledger key.

C-12 (design 2.2.1, RT1-3) has the registry record the human the kill-switch
acts for as ``operator_on_behalf_of``. The guards slice left it an ordinary key
(registry README "Declared only"), so under LOG-ONLY any shared-secret caller
could append a row carrying ``operator_on_behalf_of: don`` with no
authenticated writer (checklist items 34 and 36 read this field at the Stage 1
window audit). Now it is in ``RESERVED_KEYS``, protected exactly like
``operator_id_authenticated``: any caller-supplied copy is dropped at every
depth (``merge_payload``; the ledger's ``admit_ledger_event`` unless the caller
holds ``ledger_attribute`` reaching the event type), and the only way in is
the authenticated path: ``bind_on_behalf_of`` in a request authenticated as a
``bypass_operator_list`` identity, which ``ledger_fields`` then adds.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import pytest

from field_core import operator_auth as oa

KEY_DON = "tkv-obo-don-key-0123456789abcdef"
KEY_KSVC = "tkv-obo-ksvc-key-0123456789abcdef"
KEY_REG = "tkv-obo-reg-key-0123456789abcdef"
OBO = "operator_on_behalf_of"


def H(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(oa, "_warned", False)


@pytest.fixture(params=["log-only", "enforce"])
def armed(request, tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KSVC), "status": "active",
         "scopes": ["kill", "revive", "bypass_operator_list"]},
        {"operator_id": "svc-registry", "key_sha256": oa.key_sha256(KEY_REG), "status": "active",
         "scopes": ["ledger_attribute"], "event_prefixes": ["registry."]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if request.param == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return request.param


def _in_request(auth, fn):
    """Run fn() with ``auth`` bound and a fresh per-request context, as a guarded handler does."""
    import contextvars

    def go():
        oa.bind(auth)
        return fn()

    return contextvars.copy_context().run(go)


def _has_obo(obj) -> bool:
    if isinstance(obj, dict):
        return OBO in obj or any(_has_obo(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_obo(v) for v in obj)
    return False


def test_operator_on_behalf_of_is_a_reserved_key():
    assert OBO in oa.RESERVED_KEYS


def test_a_caller_supplied_on_behalf_of_is_dropped_by_merge_payload_at_every_depth(armed):
    forged = {"to": "killed", OBO: "don", "nested": {OBO: "don", "list": [{OBO: "don"}]}}
    out = oa.merge_payload(forged)
    assert not _has_obo(out) and out["to"] == "killed", out


@pytest.mark.parametrize("event_type", ["registry.status_changed", "registry.updated", "kill.agent", "custom.note"])
def test_the_ledger_strips_on_behalf_of_from_a_caller_without_ledger_attribute(armed, event_type):
    """The shared-secret HTTP caller with no operator identity, and a human with ``*`` (which
    does not imply ledger_attribute): the key is stripped at every depth, the rest is kept."""
    forged = {"to": "killed", OBO: "don", "nested": {OBO: "don"}}
    for headers in ({}, H("don", KEY_DON), H("svc-killswitch", KEY_KSVC)):
        out = oa.admit_ledger_event(event_type, dict(forged), headers)
        assert not _has_obo(out) and out["to"] == "killed", (headers, out)


def test_the_ledger_keeps_on_behalf_of_only_inside_the_writers_ledger_attribute_reach(armed):
    p = {"to": "killed", OBO: "don", "operator_id_authenticated": "svc-killswitch"}
    assert oa.admit_ledger_event("registry.status_changed", dict(p), H("svc-registry", KEY_REG))[OBO] == "don"
    assert OBO not in oa.admit_ledger_event("kill.agent", dict(p), H("svc-registry", KEY_REG))
    # never on an operator.* record, whoever writes it
    rec = oa.admit_ledger_event("operator.refused", {"action": "kill", OBO: "don"}, H("svc-registry", KEY_REG))
    assert OBO not in rec


def test_only_a_bypass_identity_can_bind_it_and_then_ledger_fields_carries_it(armed):
    ksvc = oa.authenticate(H("svc-killswitch", KEY_KSVC), "kill")
    don = oa.authenticate(H("don", KEY_DON), "kill")

    def bind_then_merge(value):
        bound = oa.bind_on_behalf_of(value)
        return bound, oa.merge_payload({"to": "killed", OBO: "mallory"})

    bound, out = _in_request(ksvc, lambda: bind_then_merge("don"))
    assert bound == "don" and out[OBO] == "don"                       # the bound value, not the forged one
    assert out["operator_id_authenticated"] == "svc-killswitch"
    for auth in (don, oa.OperatorAuth(oa.mode())):                     # "*" human; unauthenticated
        bound, out = _in_request(auth, lambda: bind_then_merge("don"))
        assert bound is None and OBO not in out, (auth, out)
    for bad in ("fok_" + "x" * 20, "two words", "", "a" * 60, None, 7):
        bound, out = _in_request(ksvc, lambda: bind_then_merge(bad))
        assert bound is None and OBO not in out, (bad, out)


def test_a_binding_never_outlives_its_request(armed):
    ksvc = oa.authenticate(H("svc-killswitch", KEY_KSVC), "kill")
    assert _in_request(ksvc, lambda: oa.bind_on_behalf_of("don")) == "don"
    # the next request, with the same identity, binds nothing and so records nothing
    out = _in_request(ksvc, lambda: oa.merge_payload({"to": "active"}))
    assert OBO not in out


def test_flags_off_nothing_is_bound_and_payloads_are_untouched():
    p = {"to": "killed", OBO: "don"}
    assert oa.merge_payload(p) is p                                     # byte-identical, as before
    assert oa.admit_ledger_event("registry.status_changed", p, {}) is p
    assert _in_request(oa.NO_AUTH, lambda: oa.bind_on_behalf_of("don")) is None


def test_the_binding_counts_only_while_a_bypass_identity_is_bound(armed):
    """A later bind of another identity in the same context (an in-process CLI, a nested
    call) must not inherit the kill-switch's on-behalf-of name."""
    ksvc = oa.authenticate(H("svc-killswitch", KEY_KSVC), "kill")
    don = oa.authenticate(H("don", KEY_DON), "kill")

    def go():
        assert oa.bind_on_behalf_of("don") == "don"
        oa.bind(don)
        return oa.merge_payload({"to": "killed"})

    out = _in_request(ksvc, go)
    assert OBO not in out and out["operator_id_authenticated"] == "don", out
