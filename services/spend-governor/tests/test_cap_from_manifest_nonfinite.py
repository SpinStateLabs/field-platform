"""S6-5: ``SpendCapConfig.from_manifest`` with a non-finite or absurd ``spend_cap.limit`` is a ``ValueError`` (the CLI's
``error:`` line, exit 1, nothing PUT), never an ``OverflowError`` traceback."""

from __future__ import annotations

import math

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import spend_governor.cli as cli_mod
from field_core.manifest import FieldManifest
from field_core.templates_api import template_data
from spend_governor.api import create_app
from spend_governor.core import GovernorStore, SpendCapConfig

AGENT = "invoicing-agent"


def manifest(limit):
    data = template_data("financial-agent")
    data["enforcement"]["spend_cap"]["limit"] = limit
    return FieldManifest.from_dict(data)


@pytest.mark.parametrize("limit", [float("inf"), float("-inf"), float("nan"), 1e308, 1.7e307, 1e30, 1e13, 1e12 + 1])
def test_a_non_finite_or_absurd_limit_is_a_value_error_not_an_overflow(limit):
    try:
        m = manifest(limit)
    except ValueError:
        return                                  # the manifest itself refused it: also fine
    with pytest.raises(ValueError) as e:
        SpendCapConfig.from_manifest(m, AGENT)
    assert not isinstance(e.value, OverflowError)


def test_the_finite_message_is_named_for_inf_and_overflow():
    for limit in (float("inf"), 1e308):
        with pytest.raises(ValueError, match="finite"):
            SpendCapConfig.from_manifest(manifest(limit), AGENT)


@pytest.mark.parametrize("limit,cents", [(500.0, 50_000), (0.01, 1), (1234.56, 123_456), (1e10, 10**12)])
def test_good_limits_are_unchanged(limit, cents):
    assert SpendCapConfig.from_manifest(manifest(limit), AGENT).limit_cents == cents


def test_sub_cent_precision_is_still_refused():
    with pytest.raises(ValueError, match="sub-cent"):
        SpendCapConfig.from_manifest(manifest(0.005), AGENT)


# ---- the CLI ---------------------------------------------------------------------------------------------------------

class Router:
    def __init__(self, client):
        self.client, self.puts = client, []

    def put(self, url, json=None, timeout=None, headers=None):
        self.puts.append(url)
        return self.client.put(url.replace("http://127.0.0.1:8006", ""), json=json)

    def get(self, url, params=None, timeout=None, headers=None):
        return self.client.get(url.replace("http://127.0.0.1:8006", ""), params=params)

    def post(self, url, json=None, timeout=None, headers=None):
        return self.client.post(url.replace("http://127.0.0.1:8006", ""), json=json)


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_GOVERNOR_URL", raising=False)
    client = TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3")))
    router = Router(client)
    monkeypatch.setattr(cli_mod, "httpx", router)

    def run(limit_text):
        data = template_data("financial-agent")
        data["enforcement"]["spend_cap"]["limit"] = 1  # placeholder, replaced in the text below
        path = tmp_path / "m.yaml"
        text = yaml.safe_dump(data, sort_keys=False).replace("limit: 1\n", f"limit: {limit_text}\n", 1)
        assert f"limit: {limit_text}" in text
        path.write_text(text, encoding="utf-8")
        return CliRunner().invoke(cli_mod.app, ["set-cap", AGENT, "--from-manifest", str(path)]), router
    return run


@pytest.mark.parametrize("text", [".inf", "-.inf", ".nan", "1e308", "1e30"])
def test_set_cap_from_manifest_refuses_cleanly_and_puts_nothing(cli, text):
    r, router = cli(text)
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert router.puts == []
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error:"), r.output
    assert "input_value" not in r.output


def test_set_cap_from_manifest_still_works_for_a_good_limit(cli):
    r, router = cli("500")
    assert r.exit_code == 0, r.output
    assert router.puts
