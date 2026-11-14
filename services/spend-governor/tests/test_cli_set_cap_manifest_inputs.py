"""S9-12: `set-cap --from-manifest` derives the cap, so it must not silently ignore --limit-cents, --period or
--escalate-at-pct (exit 2, nothing sent), and a missing or invalid manifest is one line and exit 1, never a
traceback. In every refusal the governor holds no cap for the agent."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import spend_governor.cli as cli_mod
from field_core.templates_api import template_data
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "invoicing-agent"


class _Router:
    """Route the CLI's module-level httpx calls into the in-process app and count them."""

    def __init__(self, client):
        self.client, self.calls = client, 0

    def _path(self, url):
        return url.replace("http://127.0.0.1:8006", "")

    def put(self, url, json=None, timeout=None, headers=None):
        self.calls += 1
        return self.client.put(self._path(url), json=json)

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls += 1
        return self.client.get(self._path(url), params=params)

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls += 1
        return self.client.post(self._path(url), json=json)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_GOVERNOR_URL", raising=False)
    store = GovernorStore(tmp_path / "spend.sqlite3")
    client = TestClient(create_app(store=store))
    router = _Router(client)
    monkeypatch.setattr(cli_mod, "httpx", router)

    def run(*args):
        return CliRunner().invoke(cli_mod.app, ["set-cap", AGENT, *args])

    yield run, client, router, tmp_path
    store.close()


def _good_manifest(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(template_data("financial-agent"), sort_keys=False), encoding="utf-8")
    return path


def _no_cap(client):
    return client.get(f"/caps/{AGENT}").status_code == 404


def _clean(result, *needles):
    assert "Traceback" not in result.output
    err = result.stderr.strip()
    assert err.count("\n") == 0 and err.startswith("error:"), err
    for n in needles:
        assert n in err


@pytest.mark.parametrize("flags", [["--limit-cents", "5"], ["--period", "monthly"], ["--period", "daily"],
                                   ["--escalate-at-pct", "50"], ["--escalate-at-pct", "80"],
                                   ["--limit-cents", "5", "--period", "total", "--escalate-at-pct", "10"]])
def test_from_manifest_with_an_explicit_derived_flag_is_exit_2_and_nothing_is_sent(env, flags):
    run, client, router, tmp_path = env
    result = run("--from-manifest", str(_good_manifest(tmp_path)), *flags)
    assert result.exit_code == 2, result.output
    _clean(result, "--from-manifest derives the cap", "nothing was configured")
    assert router.calls == 0 and _no_cap(client)


def test_token_and_action_limit_still_overlay_the_manifest_cap(env):
    run, client, router, tmp_path = env
    result = run("--from-manifest", str(_good_manifest(tmp_path)), "--token-limit", "1234",
                 "--action-limit", "7")
    assert result.exit_code == 0, result.output
    body = client.get(f"/caps/{AGENT}").json()
    assert body["token_limit"] == 1234 and body["action_limit"] == 7


def test_from_manifest_alone_still_configures_the_cap(env):
    run, client, _, tmp_path = env
    assert run("--from-manifest", str(_good_manifest(tmp_path))).exit_code == 0
    assert client.get(f"/caps/{AGENT}").status_code == 200


def test_explicit_flags_without_a_manifest_are_unchanged(env):
    run, client, _, _ = env
    result = run("--limit-cents", "5", "--period", "monthly", "--escalate-at-pct", "50")
    assert result.exit_code == 0, result.output
    body = client.get(f"/caps/{AGENT}").json()
    assert (body["limit_cents"], body["period"], body["escalate_at_pct"]) == (5, "monthly", 50)


def test_a_missing_manifest_is_one_line_exit_1(env):
    run, client, router, tmp_path = env
    result = run("--from-manifest", str(tmp_path / "nope.yaml"))
    assert result.exit_code == 1
    _clean(result, "FileNotFoundError", "manifest nope.yaml is unreadable or invalid", "nothing was configured")
    assert str(tmp_path) not in result.stderr
    assert router.calls == 0 and _no_cap(client)


@pytest.mark.parametrize("content,kind", [
    (b"[1, 2]\n", "ValueError"),                        # a non-mapping document
    (b"key: [unclosed\n  : :\n", "YAMLError"),          # bad YAML
    (b"\xff\xfe\x00\x01", "UnicodeDecodeError"),        # not UTF-8
    (b"", "ValueError"),                                # empty file
])
def test_an_unreadable_manifest_is_one_line_exit_1(env, content, kind):
    run, client, router, tmp_path = env
    path = tmp_path / "bad.yaml"
    path.write_bytes(content)
    result = run("--from-manifest", str(path))
    assert result.exit_code == 1
    _clean(result, "manifest bad.yaml is unreadable or invalid", "nothing was configured")
    assert router.calls == 0 and _no_cap(client)


def test_a_manifest_missing_its_agent_block_is_one_line_exit_1_without_its_text(env):
    run, client, router, tmp_path = env
    data = template_data("financial-agent")
    del data["agent"]
    data["identity"]["principal"] = "SECRET-PRINCIPAL-VALUE-9f3a"
    path = tmp_path / "noagent.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run("--from-manifest", str(path))
    assert result.exit_code == 1
    _clean(result, "ValidationError", "manifest noagent.yaml is unreadable or invalid")
    assert "SECRET-PRINCIPAL-VALUE-9f3a" not in result.output
    assert router.calls == 0 and _no_cap(client)
