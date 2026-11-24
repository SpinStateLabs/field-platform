"""S8-25: the regwatch interval has a floor. Each tick fetches every cited third-party source over
https, so a typo or bad env value such as `--every 1` must be refused, not run. 0 and negative still
mean off, and the interval the estates use (86400) is unchanged."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from compliance_crosswalk import cli as cli_mod
from compliance_crosswalk.api import MIN_EVERY_SECONDS, create_app


@pytest.fixture
def served(monkeypatch):
    """`crosswalk serve` without a real server: records the app it would have served."""
    import uvicorn
    ran = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: ran.update(app=app, **kw))
    return ran


def _serve(*args, env=None):
    return CliRunner().invoke(cli_mod.app, ["serve", *args], env=env)


def test_the_floor_is_a_named_constant_of_five_seconds():
    assert MIN_EVERY_SECONDS == 5


@pytest.mark.parametrize("value", [1, 2, 4])
def test_create_app_refuses_a_positive_interval_below_the_floor(value):
    with pytest.raises(ValueError, match="at least 5 seconds"):
        create_app(every=value)


@pytest.mark.parametrize("value", [5, 60, 86400])
def test_create_app_accepts_the_floor_and_above(value):
    assert create_app(every=value).state.every == value


@pytest.mark.parametrize("value", [0, -1, -5])
def test_zero_and_negative_still_mean_off(value):
    assert create_app(every=value).state.every == 0


def test_cli_refuses_every_1_with_one_line_and_exit_2(served):
    r = _serve("--every", "1")
    assert r.exit_code == 2
    assert "error: --every must be 0 (off) or at least 5 seconds, not 1" in r.output
    assert "Traceback" not in r.output and r.output.strip().count("\n") == 0
    assert served == {}                                   # nothing was served


def test_cli_refuses_a_bad_env_value_the_same_way(served):
    r = _serve(env={"FIELD_CROSSWALK_EVERY": "2"})
    assert r.exit_code == 2 and "not 2" in r.output and served == {}


@pytest.mark.parametrize("value", ["60", "86400", "5"])
def test_cli_accepts_the_floor_and_above(served, value):
    r = _serve("--every", value)
    assert r.exit_code == 0, r.output
    assert served["app"].state.every == int(value)


@pytest.mark.parametrize("value", ["0", "-5"])
def test_cli_zero_and_negative_are_still_off(served, value):
    r = _serve("--every", value)
    assert r.exit_code == 0, r.output
    assert served["app"].state.every == 0
