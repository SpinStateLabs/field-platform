"""S3-6: `canary serve` validates its env and flags once; a bad value exits 2
naming only the variable, and no server is created. `x3-check` never reads the
serve-only variables."""

from __future__ import annotations

import pytest

from field_agent import canary as c

SERVE_ENV = ("FIELD_CANARY_PORT", "FIELD_CANARY_WORK_EVERY", "FIELD_CANARY_HEARTBEAT_EVERY")


class Made(Exception):
    pass


@pytest.fixture()
def made(monkeypatch):
    for n in SERVE_ENV:
        monkeypatch.delenv(n, raising=False)
    box: list[dict] = []

    class Fake:
        def __init__(self, agent_id, **kw):
            box.append({"agent_id": agent_id, **kw})
            self.port = kw["port"]

        def serve_forever(self):
            return None

        def shutdown(self):
            return None

    monkeypatch.setattr(c, "CanaryAgent", Fake)
    monkeypatch.setattr(c.signal, "signal", lambda *a, **k: None)
    return box


@pytest.mark.parametrize("argv,name", [
    (["--port", "0"], "--port"), (["--port", "70000"], "--port"), (["--port", "x"], "--port"),
    (["--port", "8090.5"], "--port"),
    (["--work-every", "nan"], "--work-every"), (["--work-every", "inf"], "--work-every"),
    (["--work-every", "0"], "--work-every"), (["--work-every", "-1"], "--work-every"),
    (["--work-every", "0.05"], "--work-every"), (["--work-every", "junk"], "--work-every"),
    (["--heartbeat-every", "nan"], "--heartbeat-every"),
    (["--heartbeat-every", "-5"], "--heartbeat-every"),
    (["--heartbeat-every", "0.5"], "--heartbeat-every"),
    (["--heartbeat-every", "inf"], "--heartbeat-every"),
])
def test_a_bad_flag_exits_2_naming_it_and_creates_no_server(made, capsys, argv, name):
    assert c.main(["serve", *argv]) == 2
    err = capsys.readouterr().err
    assert err.startswith(f"error: {name} must be")
    assert made == []


@pytest.mark.parametrize("env,val", [
    ("FIELD_CANARY_PORT", "junk"), ("FIELD_CANARY_WORK_EVERY", "SECRET-junk"),
    ("FIELD_CANARY_WORK_EVERY", "nan"), ("FIELD_CANARY_HEARTBEAT_EVERY", "-1"),
])
def test_a_bad_env_value_exits_2_naming_only_the_variable(made, monkeypatch, capsys, env, val):
    monkeypatch.setenv(env, val)
    assert c.main(["serve"]) == 2
    err = capsys.readouterr().err
    assert env in err and val not in err
    assert made == []


def test_defaults_are_unchanged(made):
    assert c.main(["serve"]) == 0
    assert made == [{"agent_id": "canary-gb10", "host": "0.0.0.0", "port": c.DEFAULT_PORT,
                     "work_every": 5.0, "heartbeat_every": 0.0}]


def test_good_values_reach_the_agent(made, monkeypatch):
    monkeypatch.setenv("FIELD_CANARY_WORK_EVERY", "2.5")
    assert c.main(["serve", "--port", "9100", "--heartbeat-every", "30"]) == 0
    assert (made[0]["port"], made[0]["work_every"], made[0]["heartbeat_every"]) == (9100, 2.5, 30.0)
    assert c.main(["serve", "--work-every", "0.1", "--heartbeat-every", "0"]) == 0
    assert (made[1]["work_every"], made[1]["heartbeat_every"]) == (0.1, 0.0)


def test_x3_check_ignores_junk_serve_only_env(made, monkeypatch, capsys):
    for n in SERVE_ENV:
        monkeypatch.setenv(n, "junk")
    for n in ("FIELD_KILLSWITCH_URL", "FIELD_REGISTRY_URL", "FIELD_LEDGER_URL"):
        monkeypatch.delenv(n, raising=False)
    assert c.main(["x3-check", "--agent", "a"]) == 2
    assert "refusing:" in capsys.readouterr().out
