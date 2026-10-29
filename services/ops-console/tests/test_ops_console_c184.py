"""ops-console server side (C-184, reviewer C-171): the manifest path guard against a symlink out of the
manifest directory and at the size boundary, the console's own refusal ledger append (only a 201 counts),
what reaches the browser on an upstream exception or error body, and the registry error answer of the
manifest route. Stubs only; every key and secret here is a test value."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import (MANIFEST_MAX_BYTES, ManifestRefused, ServiceClient, create_app,
                             guarded_manifest_path)

PERIMETER = "c184-perimeter-secret-value"
OPERATOR_KEY = "c184-operator-key-0123456789abcdef"


class Stub:
    """An upstream that answers (status, body) for every call and records what it was sent."""

    def __init__(self, status=200, body=None, exc=None):
        self.status, self.body, self.exc, self.calls = status, body if body is not None else {}, exc, []

    def _answer(self, path, kw):
        self.calls.append((path, kw))
        if self.exc is not None:
            raise self.exc

        class R:
            status_code = self.status
            def json(_):  # noqa: N805
                return self.body

        return R()

    def get(self, path, **kw):
        return self._answer(path, kw)

    def post(self, path, **kw):
        return self._answer(path, kw)


def sc(stub) -> ServiceClient:
    return ServiceClient(client=stub, base_url="http://t")


def console(**services) -> TestClient:
    stub = sc(Stub())
    args = dict(registry=stub, ledger=stub, delegation=stub, governor=stub, killswitch=stub, sentinel=stub,
                lifecycle=stub, attest=stub, crosswalk=stub, federation=stub, replay=stub, gateway=stub)
    args.update(services)
    return TestClient(create_app(**args))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def dirs(tmp_path):
    mdir, outside = tmp_path / "manifests", tmp_path / "outside"
    mdir.mkdir()
    outside.mkdir()
    return mdir, outside


def _symlink(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this OS or account cannot create symlinks")


# --- F-C171-1: a symlink inside the manifest directory pointing out ---------------------------------


def test_a_symlink_inside_the_manifest_dir_to_a_file_outside_is_refused(dirs):
    """The target has a manifest suffix and is a file, so the suffix and size checks do not stop it; a
    containment check does. There are two and they are redundant here (``Path.resolve`` follows the link in
    both), so forcing either alone still passes; the two patched-resolve tests below pin each on its own."""
    mdir, outside = dirs
    (outside / "secret.yaml").write_text("not: a manifest, a private file\n", encoding="utf-8")
    _symlink(mdir / "link.yaml", outside / "secret.yaml")
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "link.yaml")
    assert e.value.status == 403 and "outside FIELD_MANIFEST_DIR" in e.value.reason


def test_the_manifest_route_does_not_return_the_file_a_symlink_points_at(dirs):
    mdir, outside = dirs
    (outside / "secret.yaml").write_text("private: PRIVATE-FILE-CONTENT\n", encoding="utf-8")
    _symlink(mdir / "link.yaml", outside / "secret.yaml")
    reg = Stub(200, {"agent_id": "a1", "manifest_ref": "link.yaml"})
    r = console(registry=sc(reg), manifest_dir=mdir).get("/api/agents/a1/manifest")
    assert r.status_code == 403 and "outside FIELD_MANIFEST_DIR" in r.text
    assert "PRIVATE-FILE-CONTENT" not in r.text


def test_a_symlink_to_a_file_inside_the_dir_is_read(dirs):
    """The guard is containment, not "no symlinks": a link within the directory still resolves."""
    mdir, _ = dirs
    (mdir / "real.yaml").write_text("a: 1\n", encoding="utf-8")
    _symlink(mdir / "alias.yaml", mdir / "real.yaml")
    assert guarded_manifest_path(mdir, "alias.yaml").name == "real.yaml"


# --- F-C171-1: MANIFEST_MAX_BYTES boundary -----------------------------------------------------------


def test_a_manifest_of_exactly_the_maximum_size_is_read_and_one_byte_more_is_refused(dirs):
    mdir, _ = dirs
    (mdir / "exact.yaml").write_bytes(b"a" * MANIFEST_MAX_BYTES)
    (mdir / "over.yaml").write_bytes(b"a" * (MANIFEST_MAX_BYTES + 1))
    assert guarded_manifest_path(mdir, "exact.yaml").name == "exact.yaml"
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "over.yaml")
    assert e.value.status == 403 and "larger than" in e.value.reason


# --- F-C171-3: the console's own refusal append counts only a 201 ----------------------------------


def _refusal(ledger_status: int):
    """One ENFORCE refusal (no credential) at the console; the ledger answers ``ledger_status``."""
    led = Stub(ledger_status, {"ok": True})
    c = console(ledger=sc(led), killswitch=sc(Stub()))
    os.environ[oa.ENV_REQUIRE] = "1"
    try:
        r = c.post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"})
        health = c.get("/health").json()
    finally:
        del os.environ[oa.ENV_REQUIRE]
    return r, health, led


def test_a_201_ledger_answer_is_recorded_and_not_dropped():
    r, health, led = _refusal(201)
    assert r.status_code == 401
    assert health["refused_count"] == 1 and health["dropped_refused_records"] == 0
    assert [c[0] for c in led.calls] == ["/events"]


@pytest.mark.parametrize("status", [200, 202, 400, 401, 403, 500, 503])
def test_any_other_ledger_answer_is_counted_as_a_dropped_record_and_the_refusal_stands(status):
    r, health, _ = _refusal(status)
    assert r.status_code == 401, "a failed ledger append must not change the refusal"
    assert health["refused_count"] == 1 and health["dropped_refused_records"] == 1


def test_an_unreachable_ledger_is_counted_as_a_dropped_record():
    led = Stub(exc=ConnectionError("ledger down"))
    c = console(ledger=sc(led))
    os.environ[oa.ENV_REQUIRE] = "1"
    try:
        assert c.post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"}).status_code == 401
        assert c.get("/health").json()["dropped_refused_records"] == 1
    finally:
        del os.environ[oa.ENV_REQUIRE]


# --- F-C171-2: what reaches the browser on an upstream exception or error body ---------------------


def test_service_client_returns_status_0_and_the_exception_text_never_none():
    for method in ("get", "post"):
        st, data = getattr(sc(Stub(exc=RuntimeError("upstream-said-xyz"))), method)("/p")
        assert st == 0 and data == "upstream-said-xyz"


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_an_unreachable_upstream_shows_the_browser_a_502_with_no_header_secret_or_key(monkeypatch):
    """A real httpx client (so the perimeter secret really is in its headers) against a closed port; the
    operator pair rides on the request. Neither value, nor a header name, may be in what the page gets."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", PERIMETER)
    dead = ServiceClient(base_url=f"http://127.0.0.1:{_closed_port()}")
    assert PERIMETER in dead._client.headers.get("x-field-auth", ""), "the test must hold the secret in headers"
    c = console(killswitch=dead)
    r = c.post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"},
               headers={"x-field-auth": PERIMETER, oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: OPERATOR_KEY})
    assert r.status_code == 502, r.text
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]
    low = r.text.lower()  # the answer's own text; the request headers above are not part of it
    for forbidden in (PERIMETER, OPERATOR_KEY, "x-field-auth", "x-field-operator"):
        assert forbidden.lower() not in low, forbidden


def test_an_upstream_error_status_and_body_pass_through_unchanged():
    ks = Stub(409, {"detail": "already killed"})
    r = console(killswitch=sc(ks)).post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"})
    assert r.status_code == 409 and r.json() == {"detail": {"detail": "already killed"}}  # HTTPException(detail=body)


def test_an_upstream_exception_text_is_the_502_detail():
    ks = Stub(exc=ConnectionError("no route to upstream"))
    r = console(killswitch=sc(ks)).post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"})
    assert r.status_code == 502 and r.json() == {"detail": "no route to upstream"}


# --- F-C171-4: the manifest route and a registry error answer ---------------------------------------


@pytest.mark.parametrize("status, expect", [(404, 404), (500, 500), (503, 503), (0, 502)])
def test_a_registry_error_answer_is_not_read_as_an_agent_record(dirs, status, expect):
    """The error body carries a ``manifest_ref``: a route that treated it as a record would answer 200."""
    mdir, _ = dirs
    (mdir / "good.yaml").write_text("a: 1\n", encoding="utf-8")
    if status == 0:
        reg = Stub(exc=ConnectionError("registry down"))
    else:
        reg = Stub(status, {"detail": "registry error", "manifest_ref": "good.yaml"})
    r = console(registry=sc(reg), manifest_dir=mdir).get("/api/agents/a1/manifest")
    assert r.status_code == expect, r.text
    assert r.status_code != 200


def test_a_ledger_read_error_status_and_body_reach_the_page_and_an_exception_is_a_502():
    r = console(ledger=sc(Stub(503, {"detail": "ledger busy"}))).get("/api/events")
    assert r.status_code == 503 and r.json() == {"detail": {"detail": "ledger busy"}}
    r = console(ledger=sc(Stub(exc=ConnectionError("ledger unreachable")))).get("/api/events")
    assert r.status_code == 502 and r.json() == {"detail": "ledger unreachable"}


def test_an_upstream_answer_of_200_or_201_is_returned_to_the_page():
    for status in (200, 201):
        r = console(killswitch=sc(Stub(status, {"killed": True}))).post(
            "/api/agents/a1/kill", json={"operator": "Don", "reason": "r"})
        assert r.status_code == 200 and r.json() == {"killed": True}


# --- C-270 (reviewer C-239 P2): the two containment checks, each pinned on its own -----------------------


def test_a_second_resolve_that_lands_outside_is_refused_by_the_check_after_it(dirs, monkeypatch):
    """The checks are redundant for a real symlink (``Path.resolve`` follows it in both), so a symlink test
    cannot tell them apart. Here the first resolve stays inside and the second (``strict=True``) answers a
    file outside the directory, as a link swapped in between the two would: only the second check stops it
    (mutant: ``if not real.is_relative_to(base)`` forced False)."""
    mdir, outside = dirs
    (mdir / "ok.yaml").write_text("a: 1\n", encoding="utf-8")
    (outside / "secret.yaml").write_text("private: PRIVATE-FILE-CONTENT\n", encoding="utf-8")
    real_resolve, calls = Path.resolve, []

    def resolve(self, strict=False):
        answer = real_resolve(self, strict=strict)
        if self.name == "ok.yaml":
            calls.append(strict)
            if strict:
                return real_resolve(outside / "secret.yaml", strict=True)
        return answer

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "ok.yaml")
    assert calls == [False, True] and e.value.status == 403 and "outside FIELD_MANIFEST_DIR" in e.value.reason


def test_a_first_resolve_that_lands_outside_is_refused_by_the_check_before_the_existence_read(dirs, monkeypatch):
    """The first check runs BEFORE existence (no file-existence oracle): it refuses an outside answer with a
    403 and the strict resolve is never reached (mutant: the first check forced False)."""
    mdir, outside = dirs
    (mdir / "ok.yaml").write_text("a: 1\n", encoding="utf-8")
    real_resolve, calls = Path.resolve, []

    def resolve(self, strict=False):
        if self.name == "ok.yaml":
            calls.append(strict)
            if not strict:
                return outside / "secret.yaml"
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "ok.yaml")
    assert calls == [False] and e.value.status == 403 and "outside FIELD_MANIFEST_DIR" in e.value.reason


# --- C-270 (reviewer C-239 P3): the console's signed refusal append --------------------------------------


def _signer_env(monkeypatch, tmp_path):
    from field_core.signing import generate_keypair

    priv, pub = generate_keypair()
    key = tmp_path / "console.pem"
    key.write_text(priv, encoding="ascii")
    monkeypatch.setenv("FIELD_LEDGER_CALLER_ID", "console")
    monkeypatch.setenv("FIELD_LEDGER_CALLER_KEY", str(key))
    return pub


class _Led(Stub):
    """A ledger client with the headers a real httpx client would carry (the perimeter secret)."""

    def __init__(self, status=201, exc=None):
        super().__init__(status, {"ok": True}, exc)
        self.headers = {"x-field-auth": PERIMETER}


def _refuse(led, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    c = console(ledger=sc(led), killswitch=sc(Stub()))
    assert c.post("/api/agents/a1/kill", json={"operator": "Don", "reason": "r"}).status_code == 401
    return c


def _wait_for(predicate, seconds=5.0):
    import time

    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_with_a_refusal_signer_the_posted_body_is_signed_and_verifies(tmp_path, monkeypatch):
    from field_core.signing import verify_caller_signature

    pub = _signer_env(monkeypatch, tmp_path)
    led = _Led()
    _refuse(led, monkeypatch)
    assert _wait_for(lambda: led.calls)
    path, kw = led.calls[0]
    body = kw["json"]
    assert path == "/events" and body["event_type"] == "operator.refused" and body["agent_id"] == "a1"
    assert body["caller_id"] == "console" and body["caller_ts"] and body["caller_signature"]
    assert verify_caller_signature(body, pub), "the signature does not verify over the posted event"
    tampered = dict(body, payload=dict(body["payload"], reason="other"))
    assert not verify_caller_signature(tampered, pub)


def test_without_a_refusal_signer_the_posted_body_is_the_three_unsigned_keys(monkeypatch):
    monkeypatch.delenv("FIELD_LEDGER_CALLER_ID", raising=False)
    monkeypatch.delenv("FIELD_LEDGER_CALLER_KEY", raising=False)
    led = _Led()
    _refuse(led, monkeypatch)
    assert _wait_for(lambda: led.calls)
    assert set(led.calls[0][1]["json"]) == {"event_type", "payload", "agent_id"}


@pytest.mark.parametrize("answer, shown", [(503, "status=503"), (403, "status=403"), (0, "status=LedgerUnreachableError")])
def test_a_failed_refusal_append_is_logged_with_the_http_status_or_the_failure_class(
        tmp_path, monkeypatch, caplog, answer, shown):
    """status 0 (the ledger could not be reached) becomes ``status_code=None``, so the log names the failure
    class; a real status is logged as the number (mutant: ``status_code=status or None`` without the ``or``)."""
    import logging

    led = _Led(status=answer) if answer else _Led(exc=ConnectionError("ledger down"))
    with caplog.at_level(logging.WARNING):
        c = _refuse(led, monkeypatch)
        assert _wait_for(lambda: c.get("/health").json()["dropped_refused_records"] == 1)
        assert _wait_for(lambda: any("operator.refused ledger append failed" in r.getMessage()
                                     for r in caplog.records))
    line = next(r.getMessage() for r in caplog.records if "operator.refused ledger append failed" in r.getMessage())
    assert shown in line, line
    assert "ledger down" not in line, "the failure's message must never be logged"
