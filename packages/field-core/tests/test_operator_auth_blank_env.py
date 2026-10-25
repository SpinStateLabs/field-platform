"""Phase G plumbing: compose forwards both flags as ``${VAR:-}``, so a container
sees them as the EMPTY STRING when the estate has not armed them. Blank must be
exactly mode OFF (byte-identical to unset), never log-only and never enforce."""

from __future__ import annotations

import pytest

from field_core import operator_auth as oa


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n"])
def test_blank_registry_is_mode_off_like_unset(monkeypatch, blank):
    monkeypatch.setenv(oa.ENV_REGISTRY, blank)
    assert oa.registry_path() is None
    assert oa.mode() == oa.OFF


@pytest.mark.parametrize("off", ["", " ", "0", "false", "no", "off", "2", "enforce"])
def test_blank_or_non_truthy_require_is_off(monkeypatch, off):
    monkeypatch.setenv(oa.ENV_REQUIRE, off)
    assert oa.mode() == oa.OFF


def test_both_blank_together_is_off(monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, "")
    monkeypatch.setenv(oa.ENV_REQUIRE, "")
    assert oa.mode() == oa.OFF
    assert oa.authenticate({}, "kill") is oa.NO_AUTH
    assert oa.merge_payload({"a": 1}) == {"a": 1}


def test_blank_require_does_not_disturb_log_only(monkeypatch, tmp_path):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.ENV_REQUIRE, "")
    assert oa.mode() == oa.LOG_ONLY


@pytest.mark.parametrize("on", ["1", "true", "YES", " on "])
def test_require_truthy_still_enforces_with_a_blank_registry(monkeypatch, on):
    monkeypatch.setenv(oa.ENV_REGISTRY, "")
    monkeypatch.setenv(oa.ENV_REQUIRE, on)
    assert oa.mode() == oa.ENFORCE
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate({"x-field-operator": "don", "x-field-operator-key": "k"}, "kill")
    assert e.value.status == 503      # unset registry under ENFORCE: never fail-open


@pytest.mark.parametrize("off", ["0", "false", "FALSE", "False", "no", "No", "off", "OFF", " off ", " 0 ", "\tfalse\n"])
def test_registry_off_spellings_are_mode_off_like_require(monkeypatch, off):
    monkeypatch.setenv(oa.ENV_REGISTRY, off)
    assert oa.registry_path() is None
    assert oa.mode() == oa.OFF


def test_a_real_path_still_arms_log_only(monkeypatch):
    for p in ("/run/field/operators.json", "D:\ops\o.json", "offices.json", "0.json", "nothing"):
        monkeypatch.setenv(oa.ENV_REGISTRY, p)
        assert oa.mode() == oa.LOG_ONLY, p
