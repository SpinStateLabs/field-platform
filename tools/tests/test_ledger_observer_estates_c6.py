"""Phase G C-6 follow-up: the ledger's operator observer is switched ON on both estates.

PR #41 merged the observer (``sealed_ledger/operator_observer.py``) OFF unless
FIELD_LEDGER_OBSERVE_EVERY is set, and nothing set it, so C-6 was inert (the
guards ruling: "blocks Stage 1"). These pins read the shipped descriptors (no
docker, no network) and prove, for the GB10 compose estate (base file + GB10
override, merged the way Compose merges) and for the Fly entrypoint:

* the ledger, and only the ledger, gets FIELD_LEDGER_OBSERVE_EVERY with a
  default that ARMS the observer (60 s) and FIELD_LEDGER_OBSERVE_HEALTH naming
  every other service that reports an operator block on ``/health`` (found from
  the code, not from a list here), each at the port its own ``serve`` command
  listens on;
* setting them arms nothing else: the operator flags stay blank, the ledger's
  own operator mode is still ``off``, and the observer's GETs carry no header.

The behaviour of an armed observer against real HTTP ``/health`` answers is
pinned in ``services/sealed-ledger/tests/test_operator_observer_c6_serve.py``;
CI's compose-smoke, compose-upgrade-smoke and fly-image-smoke jobs check the
rows on the real containers."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "integration" / "demo"
FLY = REPO / "integration" / "fly"
EVERY = "FIELD_LEDGER_OBSERVE_EVERY"
HEALTH = "FIELD_LEDGER_OBSERVE_HEALTH"
EVERY_VALUE = "${FIELD_LEDGER_OBSERVE_EVERY:-60}"
INTERVAL_S = 60
FLAGS = ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE")

#: service source dir -> compose service name == the CLI the Fly entrypoint runs
CLI = {
    "agent-registry": "registry", "sealed-ledger": "ledger", "delegation-authority": "delegation",
    "kill-switch": "killswitch", "spend-governor": "governor", "federation-broker": "fedbroker",
    "ops-console": "console", "lifecycle-manager": "lifecycle",
}


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor(
    "!override", lambda l, n: l.construct_sequence(n)
    if isinstance(n, yaml.SequenceNode) else l.construct_scalar(n))


def _compose(name: str) -> dict:
    return yaml.load((DEMO / name).read_text(encoding="utf-8"), Loader=_Loader)


def _env(svc: dict) -> dict:
    e = svc.get("environment") or {}
    if isinstance(e, list):
        e = dict(x.split("=", 1) for x in e)
    return {k: ("" if v is None else str(v)) for k, v in e.items()}


def _merged_env() -> dict[str, dict]:
    """environment merges by key, the override winning (as Compose does)."""
    base, over = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")
    out: dict[str, dict] = {}
    for name in set(base["services"]) | set(over["services"]):
        env: dict = {}
        for doc in (base, over):
            env.update(_env(doc["services"].get(name) or {}))
        out[name] = env
    return out


def _compose_default(value: str) -> str:
    """What Compose substitutes for ``${VAR:-default}`` when VAR is unset or empty."""
    m = re.fullmatch(r"\$\{[A-Z_]+:-([^}]*)\}", value)
    assert m, value
    return m.group(1)


def operator_block_services() -> set[str]:
    """Every service whose app reports the C-8 operator block (operator_health.install),
    read from the code, so a new one cannot be left unobserved."""
    found = set()
    for api in (REPO / "services").glob("*/src/*/api.py"):
        if "operator_health.install(" in api.read_text(encoding="utf-8"):
            found.add(api.parts[-4])
    return found


def test_the_operator_block_services_are_the_eight_flag_bearing_services():
    assert operator_block_services() == set(CLI), operator_block_services()


def _compose_port(svc: dict) -> int:
    cmd = svc["command"].split()
    assert cmd[1:2] == ["serve"] and "--port" in cmd, svc["command"]
    return int(cmd[cmd.index("--port") + 1])


def _expected_compose_targets(base: dict) -> list[tuple[str, str]]:
    return sorted((src, f"http://{CLI[src]}:{_compose_port(base['services'][CLI[src]])}")
                  for src in operator_block_services() - {"sealed-ledger"})


def _check_armed(every_raw: str, health_raw: str, expected: list[tuple[str, str]]) -> None:
    from sealed_ledger import operator_observer as ob

    assert ob.interval_from_env(every_raw) == INTERVAL_S          # armed, and not floored
    targets = ob.parse_targets(health_raw)                         # nothing skipped as malformed
    assert sorted(targets) == expected, targets
    assert len(targets) == len(health_raw.split(","))
    # header-less, credential-less plain URLs: no userinfo, query or fragment
    assert not any(c in health_raw for c in "@?#"), health_raw


@pytest.mark.parametrize("topology", ["base", "gb10-merged"])
def test_compose_ledger_runs_the_observer_against_every_other_operator_block_service(topology):
    base = _compose("docker-compose.yml")
    env = _env(base["services"]["ledger"]) if topology == "base" else _merged_env()["ledger"]
    assert env.get(EVERY) == EVERY_VALUE, env.get(EVERY)
    _check_armed(_compose_default(env[EVERY]), env[HEALTH], _expected_compose_targets(base))


def test_only_the_ledger_carries_the_observer_variables_in_any_compose_file():
    base, over = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")
    for doc in (base, over):
        for key, block in doc.items():
            if key.startswith("x-") and isinstance(block, dict):
                assert not {EVERY, HEALTH} & set(_env(block)), key
    for name, env in _merged_env().items():
        if name != "ledger":
            assert not {EVERY, HEALTH} & set(env), name
    # the GB10 override leaves the base file's values as they are
    assert not {EVERY, HEALTH} & set(_env(over["services"].get("ledger") or {}))


def _entry_lines() -> list[str]:
    text = (FLY / "entrypoint.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _launch(cli: str) -> tuple[dict[str, str], list[str]]:
    """(per-process assignments, argv) of the one line that launches ``cli serve``."""
    lines = [ln for ln in _entry_lines() if re.search(rf"(^|\s){cli} serve ", ln)]
    assert len(lines) == 1, (cli, lines)
    words = shlex.split(lines[0].rstrip("&").strip())
    assigns: dict[str, str] = {}
    while words and re.fullmatch(r"[A-Z_][A-Z0-9_]*=.*", words[0]):
        k, v = words.pop(0).split("=", 1)
        assigns[k] = v
    return assigns, words


def test_fly_ledger_process_runs_the_observer_against_every_other_operator_block_service():
    assigns, argv = _launch("ledger")
    assert argv == ["ledger", "serve", "--host", "127.0.0.1", "--port", "8002"]
    assert set(assigns) == {EVERY, HEALTH}, assigns
    assert assigns[EVERY] == EVERY_VALUE
    expected = []
    for src in operator_block_services() - {"sealed-ledger"}:
        _, a = _launch(CLI[src])
        assert a[a.index("--host") + 1] == "127.0.0.1"
        expected.append((src, f"http://127.0.0.1:{a[a.index('--port') + 1]}"))
    _check_armed(_compose_default(assigns[EVERY]), assigns[HEALTH], sorted(expected))


def test_fly_sets_the_observer_for_the_ledger_process_only():
    import tomllib

    for ln in _entry_lines():
        if EVERY in ln or HEALTH in ln:
            assert re.search(r"(^|\s)ledger serve ", ln) and not ln.lstrip().startswith("export"), ln
    fly_env = tomllib.loads((FLY / "fly.toml").read_text(encoding="utf-8")).get("env", {})
    assert not {EVERY, HEALTH} & set(fly_env)


def test_the_observer_settings_arm_no_operator_flag_and_leave_the_ledger_mode_off(tmp_path, monkeypatch):
    """The estates' observer values, with the operator flags exactly as the descriptors
    resolve them (blank): the observer is armed, and the ledger's operator mode is OFF."""
    from fastapi.testclient import TestClient

    from field_core import operator_auth as oa
    from sealed_ledger.api import create_app
    from sealed_ledger.store import LedgerStore

    ledger = _merged_env()["ledger"]
    for f in FLAGS:
        assert ledger[f] == "${%s:-}" % f                              # still blank in compose
    assigns, _ = _launch("ledger")
    assert not set(FLAGS) & set(assigns)                               # nothing new on Fly's ledger line
    for name in list(__import__("os").environ):
        if name.startswith("FIELD_OPERATOR"):
            monkeypatch.delenv(name, raising=False)
    for f in FLAGS:
        monkeypatch.setenv(f, _compose_default(ledger[f]))            # "" == unset
    monkeypatch.setenv(EVERY, _compose_default(ledger[EVERY]))
    monkeypatch.setenv(HEALTH, ledger[HEALTH])
    seen_urls: list[str] = []
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"),
                     observe_fetch=lambda url: seen_urls.append(url) or None)
    assert app.state.operator_observer is not None and app.state.operator_observer_every == INTERVAL_S
    assert oa.mode() == oa.OFF
    app.state.operator_observer.observe_once()
    assert len(seen_urls) == len(operator_block_services()) - 1      # each other service, once
    h = TestClient(app).get("/health").json()
    assert h["operator_mode"] == "off" and h["operator_registry_sha256_prefix"] is None
    [m] = TestClient(app).get("/events", params={"event_type": "operator.mode_changed"}).json()
    assert m["payload"] == {"service": "sealed-ledger", "mode": "off", "previous_mode": None,
                            "startup": True, "observed_from": "health"}


def test_the_ci_check_script_expects_exactly_the_operator_block_services():
    import importlib.util

    path = DEMO / "fixtures" / "c6-observer" / "check_rows.py"
    spec = importlib.util.spec_from_file_location("c6_check_rows", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.SERVICES) == operator_block_services() and len(mod.SERVICES) == len(set(mod.SERVICES))


def _check_rows_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("c6_check_rows_l2", DEMO / "fixtures" / "c6-observer" / "check_rows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("bad", [None, "mode-row-not-startup", "registry-row-not-startup", "mode-row-previous-set",
                                 "mode-row-other-source"])
def test_the_ci_check_script_requires_each_first_row_to_be_a_startup_observation(monkeypatch, bad):
    """Review L2: check_rows.py must FAIL when a service's first row is not a start-up
    observation (startup true, previous_mode null, observed_from health)."""
    mod = _check_rows_module()

    def rows(event_type):
        out = []
        for s in mod.SERVICES:
            p = {"service": s, "mode": "off", "previous_mode": None, "startup": True, "observed_from": "health"}
            if event_type == mod.REGISTRY_EVENT:
                p = {"service": s, "mode": "off", "registry_sha256_prefix": None, "registry_rows": None,
                     "startup": True, "observed_from": "health"}
            if s == "kill-switch" and bad:
                if bad == "mode-row-not-startup" and event_type == mod.MODE_EVENT:
                    p["startup"] = False
                if bad == "registry-row-not-startup" and event_type == mod.REGISTRY_EVENT:
                    p["startup"] = False
                if bad == "mode-row-previous-set" and event_type == mod.MODE_EVENT:
                    p["previous_mode"] = "enforce"
                if bad == "mode-row-other-source" and event_type == mod.MODE_EVENT:
                    p["observed_from"] = "http"
            out.append({"event_type": event_type, "agent_id": None, "payload": p})
        return out

    monkeypatch.setattr(mod, "_events", lambda base, event_type, secret: rows(event_type))
    problems = mod.check("http://ledger.invalid", 0, "off", None)
    if bad is None:
        assert problems == []
    else:
        assert len(problems) == 1 and problems[0].startswith("kill-switch: first operator."), problems
