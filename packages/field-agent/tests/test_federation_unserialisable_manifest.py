"""S7-4: YAML parses an unquoted `expiry: 2027-01-01` to a date, which the JSON body cannot carry.
That is a caller error raised before any request, not 'federation-broker unreachable': the broker
was never asked."""

from __future__ import annotations

import datetime
import json

import pytest
import typer
from typer.testing import CliRunner

from field_agent import federation as fed
from field_agent.federation import CrossingBlocked, FederationClient

SCOPE = "exchange invoice status"


class Recorder:
    """A transport double that counts every request and answers a fixed ALLOW."""

    def __init__(self):
        self.posts = []

    def post(self, url, json=None, headers=None, **kw):
        self.posts.append((url, json))

        class Resp:
            status_code = 200
            text = ""

            def json(self_inner):
                return {"decision": "ALLOW", "reasons": []}
        return Resp()


def _client(rec):
    return FederationClient(client=rec, base_url="http://t")


def _call(client, manifest):
    return client.cross("our-agent", "Borealis Example Corp", SCOPE, "invoice metadata", manifest)


def _write(tmp_path, expiry_line):
    path = tmp_path / "m.yaml"
    path.write_text(f"agent:\n  name: our-agent\ndelegation:\n  {expiry_line}\n", encoding="utf-8")
    return path


def test_an_unquoted_date_in_a_manifest_file_is_a_value_error_before_any_request(tmp_path):
    rec = Recorder()
    path = _write(tmp_path, "expiry: 2027-01-01")
    with pytest.raises(ValueError, match="not JSON-serialisable") as e:
        FederationClient.request_body("our-agent", "Borealis Example Corp", SCOPE, "d", path)
    assert str(path) in str(e.value) and "quote dates" in str(e.value)
    with pytest.raises(ValueError, match="not JSON-serialisable"):
        _call(_client(rec), path)
    assert rec.posts == []                      # nothing was sent: not 'unreachable'


def test_a_timestamp_in_a_mapping_is_the_same_error():
    rec = Recorder()
    manifest = {"delegation": {"expiry": datetime.datetime(2027, 1, 1, 12, 0)}}
    with pytest.raises(ValueError, match="not JSON-serialisable"):
        _call(_client(rec), manifest)
    assert rec.posts == []


def test_a_quoted_date_still_posts(tmp_path):
    rec = Recorder()
    path = _write(tmp_path, 'expiry: "2027-01-01"')
    assert _call(_client(rec), path)["decision"] == "ALLOW"
    assert len(rec.posts) == 1
    assert rec.posts[0][1]["manifest"]["delegation"]["expiry"] == "2027-01-01"
    json.dumps(rec.posts[0][1])


def test_it_is_not_reported_as_a_blocked_crossing(tmp_path):
    with pytest.raises(Exception) as e:
        _call(_client(Recorder()), _write(tmp_path, "expiry: 2027-01-01"))
    assert not isinstance(e.value, CrossingBlocked)


def test_the_cli_prints_a_one_line_error_and_exits_1(tmp_path, monkeypatch):
    rec = Recorder()
    app = typer.Typer()

    @app.callback()
    def _root():
        pass

    fed.register_cli(app)
    monkeypatch.setattr(fed, "_cli_client", lambda: _client(rec))
    path = _write(tmp_path, "expiry: 2027-01-01")
    result = CliRunner().invoke(app, ["cross", "our-agent", "--org", "Borealis Example Corp",
                                      "--scope", SCOPE, "--data-class", "invoice metadata",
                                      "--manifest", str(path)])
    assert result.exit_code == 1
    assert "error:" in result.output and "not JSON-serialisable" in result.output
    assert "unreachable" not in result.output
    assert rec.posts == []
