"""G22 (Don's ruling D-12; architect decision 2026-11-05): FIELD_INTERNAL_SECRET as a Stage 2 prerequisite.

The conditions the decision sets, one test group each: the mode policy (ENFORCE with the hash unset answers 404, OFF and
LOG-ONLY warn once), the hash-verified `x-field-internal` header on exactly the two internal routes, the deny counter in
`/health`, the F-C849-5 equality refusals (the perimeter secret and a read key), the header name pinned by value, the
length bound, a bad value stopping the service at start (and the runbook saying so), nothing in a compose or Fly file
holding the plain secret, and the `phase_g_check --stage 2` line. All values here are throwaway constants."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from field_core import authn
from field_core import operator_auth as oa
from field_core import operator_health as oh

REPO = Path(__file__).resolve().parents[3]
PERIMETER = "tkv-g22-perimeter-0123456789"
INTERNAL = "tkv-g22-internal-0123456789abcdef"
INTERNAL_HASH = hashlib.sha256(INTERNAL.encode()).hexdigest()
READ_KEY = "tkv-g22-read-key-0123456789abcd"
BODY = json.dumps({"operator_id": "don", "key_sha256": "0" * 64})


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE,
              authn.ENV_VAR, oh.ENV_INTERNAL_SECRET, oh.ENV_INTERNAL_SECRET_SHA256, oh.ENV_READ_KEY):
        monkeypatch.delenv(n, raising=False)
    p = tmp_path / "operators.json"
    p.write_bytes(json.dumps({"format": 1, "operators": [
        {"operator_id": "don", "key_sha256": oa.key_sha256("tkv-g22-don-0123456789abcdef"), "status": "active",
         "scopes": ["*"]}]}).encode())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))          # LOG-ONLY: the routes exist
    monkeypatch.setenv(authn.ENV_VAR, PERIMETER)
    oh._reset_internal_state()
    yield
    oh._reset_internal_state()


def enforce(monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def client() -> TestClient:
    app = FastAPI()
    authn.install(app)
    oh.install(app, ledger_getter=lambda a: None)
    return TestClient(app)


def state(c, internal=None):
    h = {authn.HEADER: PERIMETER}
    if internal is not None:
        h[oh.INTERNAL_HEADER] = internal
    return c.get(oh.ROTATION_STATE_PATH, headers=h)


def verify(c, internal=None):
    h = {authn.HEADER: PERIMETER}
    if internal is not None:
        h[oh.INTERNAL_HEADER] = internal
    return c.post(oh.VERIFY_HASH_PATH, content=BODY, headers=h)


# ---- 2. mode policy -------------------------------------------------------------------------------------------------

def test_enforce_with_the_hash_unset_answers_404_on_both_routes(monkeypatch):
    enforce(monkeypatch)
    c = client()
    for header in (None, INTERNAL, "", INTERNAL_HASH):
        assert state(c, header).status_code == 404
        assert verify(c, header).status_code == 404


def test_enforce_with_the_hash_set_and_the_right_header_answers_200(monkeypatch):
    enforce(monkeypatch)
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    assert state(c, INTERNAL).status_code == 200
    assert verify(c, INTERNAL).status_code != 404


@pytest.mark.parametrize("bad", ["", "wrong", INTERNAL + "x", INTERNAL_HASH, INTERNAL_HASH.upper(), INTERNAL[:-1]])
def test_a_wrong_empty_or_hash_valued_header_answers_404_when_the_hash_is_set(monkeypatch, bad):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    assert state(c, bad).status_code == 404 and verify(c, bad).status_code == 404


@pytest.mark.parametrize("mode", ["off", "log-only"])
def test_off_and_log_only_with_the_hash_unset_warn_once_per_process(mode, monkeypatch, caplog):
    if mode == "off":
        monkeypatch.delenv(oa.ENV_REGISTRY)
    c = client()
    with caplog.at_level(logging.WARNING, logger="field_core.operator_health"):
        for _ in range(3):
            state(c)
            verify(c)
    warnings = [r for r in caplog.records if r.name == "field_core.operator_health"]
    # OFF answers 404 before the layer is reached (the operator layer is off): nothing to warn about
    assert len(warnings) == (0 if mode == "off" else 1)
    if warnings:
        assert oh.ENV_INTERNAL_SECRET_SHA256 in warnings[0].getMessage()
        assert PERIMETER not in warnings[0].getMessage()


def test_log_only_with_the_hash_unset_still_answers_on_the_perimeter_secret_alone():
    c = client()
    assert state(c).status_code == 200 and verify(c).status_code != 404


def test_enforce_with_the_hash_unset_does_not_warn(monkeypatch, caplog):
    enforce(monkeypatch)
    c = client()
    with caplog.at_level(logging.WARNING, logger="field_core.operator_health"):
        state(c)
    assert [r for r in caplog.records if r.name == "field_core.operator_health"] == []


# ---- 4. the deny counter ----------------------------------------------------------------------------------------------

def test_every_refusal_by_the_layer_is_counted_in_health_and_a_success_is_not(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    health = oh.OperatorHealth()
    assert health.health_fields()["operator_internal_route_denied"] == 0
    state(c, "wrong")
    verify(c, "")
    state(c)
    assert health.health_fields()["operator_internal_route_denied"] == 3
    state(c, INTERNAL)
    verify(c, INTERNAL)
    assert health.health_fields()["operator_internal_route_denied"] == 3


def test_a_perimeter_refusal_or_an_off_layer_is_not_counted_as_an_internal_denial(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    assert c.get(oh.ROTATION_STATE_PATH).status_code == 401          # no perimeter secret: the middleware answers
    monkeypatch.delenv(oa.ENV_REGISTRY)
    assert state(c, INTERNAL).status_code == 404                      # the operator layer is off
    assert oh.internal_route_denied() == 0


def test_health_says_whether_the_hash_is_present_and_never_carries_it_or_the_secret(monkeypatch):
    health = oh.OperatorHealth()
    assert health.health_fields()["internal_secret_sha256_present"] is False
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    fields = health.health_fields()
    assert fields["internal_secret_sha256_present"] is True
    blob = json.dumps(fields)
    assert INTERNAL not in blob and INTERNAL_HASH not in blob and INTERNAL_HASH[:16] not in blob


# ---- 1. C-983 conditions: F-C849-5, the header pin, the length bound -------------------------------------------------

def test_the_header_name_is_pinned_by_value():
    """Callers (the rotator) hard-code it: a rename must break this test, not a deploy."""
    assert oh.INTERNAL_HEADER == "x-field-internal"


@pytest.mark.parametrize("form", ["value", "hash"])
@pytest.mark.parametrize("env", [oh.ENV_READ_KEY, oh.ENV_READ_KEY + "_KILLSWITCH"])
def test_an_internal_secret_equal_to_a_read_key_is_refused_at_install(form, env, monkeypatch):
    """F-C849-5: a second secret that is the read-tier key adds nothing."""
    monkeypatch.setenv(env, READ_KEY)
    if form == "value":
        monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, READ_KEY)
    else:
        monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, hashlib.sha256(READ_KEY.encode()).hexdigest())
    with pytest.raises(ValueError) as exc:
        client()
    assert READ_KEY not in str(exc.value)


def test_an_internal_secret_different_from_the_read_key_is_accepted(monkeypatch):
    monkeypatch.setenv(oh.ENV_READ_KEY, READ_KEY)
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    assert client() is not None


@pytest.mark.parametrize("form", ["value", "hash"])
def test_an_internal_secret_equal_to_the_perimeter_secret_is_refused_at_install(form, monkeypatch):
    if form == "value":
        monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, PERIMETER)
    else:
        monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, hashlib.sha256(PERIMETER.encode()).hexdigest())
    with pytest.raises(ValueError):
        client()


def test_the_secret_length_is_bounded(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, "a" * oh.MAX_INTERNAL_SECRET_LEN)
    assert client() is not None
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, "a" * (oh.MAX_INTERNAL_SECRET_LEN + 1))
    with pytest.raises(ValueError) as exc:
        client()
    assert "longer than" in str(exc.value) and "aaaaaaaa" not in str(exc.value)


@pytest.mark.parametrize("env,value", [(oh.ENV_INTERNAL_SECRET_SHA256, "not-hex"),
                                       (oh.ENV_INTERNAL_SECRET_SHA256, hashlib.sha256(b"").hexdigest()),
                                       (oh.ENV_INTERNAL_SECRET, "has space"),
                                       (oh.ENV_INTERNAL_SECRET, "a" * 300)])
def test_a_bad_value_stops_the_service_at_start_and_the_runbook_says_so(env, value, monkeypatch):
    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError):
        client()
    runbook = (REPO / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    section = runbook[runbook.index("## Internal secret (G22)"):]
    assert "stops the service at start" in section


# ---- 3. the holder: never a service env var, never the shared anchor ---------------------------------------------------

def _estate_files() -> list[Path]:
    return sorted([*REPO.rglob("docker-compose*.yml"), *REPO.rglob("docker-compose*.yaml"), *REPO.rglob("fly*.toml")])


def test_no_compose_or_fly_file_holds_the_plain_internal_secret_in_any_service_env():
    files = _estate_files()
    assert files, "no compose or fly file found: the scan would prove nothing"
    offenders = []
    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"FIELD_INTERNAL_SECRET(?!_SHA256)", line):
                offenders.append(f"{path.relative_to(REPO)}:{n}")
    assert offenders == []


def test_only_the_hash_name_may_appear_in_a_shared_env_anchor():
    """If the hash is wired into compose it is the `_SHA256` name, and the plain name is on no anchor (C-71)."""
    for path in _estate_files():
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^x-[\w-]*env[\w-]*:.*?(?=^\S)", text, flags=re.S | re.M):
            assert not re.search(r"FIELD_INTERNAL_SECRET(?!_SHA256)", m.group(0)), path


# ---- phase_g_check --stage 2 -----------------------------------------------------------------------------------------

def _phase_g_check():
    tools = str(REPO / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    spec = importlib.util.spec_from_file_location("phase_g_check_g22", REPO / "tools" / "phase_g_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEstate:
    def __init__(self, healths):
        self.healths, self.calls = healths, []

    def call(self, method, path, auth=True, **kw):
        self.calls.append((method, path, auth))
        answer = self.healths.get(path)
        return (200, answer) if answer is not None else (503, {})


@pytest.mark.parametrize("killswitch,registry,passed,count", [
    (True, True, True, 2), (True, False, False, 1), (False, True, False, 1), (False, False, False, 0),
    (None, True, False, 1), ("yes", "yes", False, 0)])
def test_stage_2_precondition_needs_the_hash_on_both_services(killswitch, registry, passed, count, capsys):
    pgc = _phase_g_check()
    healths = {}
    for path, value in (("/killswitch/health", killswitch), ("/registry/health", registry)):
        if value is not None:
            healths[path] = {"internal_secret_sha256_present": value}
    estate = FakeEstate(healths)
    assert pgc.stage2_precondition(estate) is passed
    assert estate.calls == [("GET", "/killswitch/health", False), ("GET", "/registry/health", False)]
    out = capsys.readouterr().out
    assert f"internal secret hash present on kill-switch and registry /health ({count} of 2)" in out
    assert ("[PASS]" if passed else "[FAIL]") in out


def test_stage_2_is_an_option_of_the_command_line_and_nothing_else_accepted():
    pgc = _phase_g_check()
    parser = pgc.build_parser()
    assert parser.parse_args(["--base", "http://x", "--stage", "2"]).stage == 2
    assert parser.parse_args(["--base", "http://x"]).stage is None
    with pytest.raises(SystemExit):
        parser.parse_args(["--base", "http://x", "--stage", "3"])
