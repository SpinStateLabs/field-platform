"""`POST /crosswalk/markdown` and `compliance-crosswalk run --markdown`: pinned over the route and the CLI (scout P-24,
tests only, no source change).

Before: only `render_markdown` was called directly; the route and the `--markdown` flag had no test, so their wiring
(text/plain, the same text, the failure statuses) was unpinned. The `*Generated:*` line carries the clock, so equality
is checked with that line removed."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import cli as cli_mod
from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import evaluate, render_markdown
from test_crosswalk import resolved_manifest   # sibling import, as other suites do

GENERATED = re.compile(r"^\*Generated:\*[^\n]*\n", re.MULTILINE)


def _stable(text: str) -> str:
    return GENERATED.sub("*Generated:* <clock>\n", text)


@pytest.fixture()
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_the_route_answers_200_text_plain_with_the_rendered_report(client):
    r = client.post("/crosswalk/markdown", json={"manifest": resolved_manifest()})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert _stable(r.text) == _stable(render_markdown(evaluate(resolved_manifest())))


def test_the_route_text_keeps_the_citation_status_and_the_ledger_of_controls(client):
    text = client.post("/crosswalk/markdown", json={"manifest": resolved_manifest()}).text
    assert "Citation status" in text and "source-grounded" in text and "pending-purchase" in text
    assert "Article 12 (Record-Keeping)" in text and "MANAGE 2.4" in text
    assert text.startswith("# Compliance crosswalk")


def test_the_route_with_an_agent_id_names_it(client):
    text = client.post("/crosswalk/markdown", json={"manifest": resolved_manifest(), "agent_id": "invoicing-agent"}).text
    assert text.startswith("# Compliance crosswalk — invoicing-agent")


def test_a_structurally_invalid_manifest_is_200_with_manifest_valid_no_never_a_500(client):
    r = client.post("/crosswalk/markdown", json={"manifest": {"agent": 5}})
    assert r.status_code == 200
    assert "*Manifest valid:* NO" in r.text


@pytest.mark.parametrize("body", [
    {"manifest": "x"}, {"manifest": None}, {"manifest": [1]}, {}, {"manifest": {}, "bogus": 1}, {"agent_id": "a"},
])
def test_a_wrong_shaped_request_is_422_not_500(client, body):
    r = client.post("/crosswalk/markdown", json=body)
    assert r.status_code == 422, (body, r.status_code)


def test_a_422_repeats_no_caller_text(client):
    marker = "MADE-UP-MARKER-0123456789"
    r = client.post("/crosswalk/markdown", json={"manifest": marker})
    assert r.status_code == 422 and marker not in r.text


def test_the_json_route_and_the_markdown_route_agree_on_the_counts(client):
    body = {"manifest": resolved_manifest()}
    report = client.post("/crosswalk", json=body).json()
    text = client.post("/crosswalk/markdown", json=body).text
    declared = sum(1 for c in report["controls"] if c["declared"])
    assert f"{declared}/{len(report['controls'])} declared" in text


# -- the CLI ------------------------------------------------------------------------------------------------------


@pytest.fixture()
def manifest_file(tmp_path):
    import yaml
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(resolved_manifest(), sort_keys=False), encoding="utf-8")
    return p


def test_the_cli_writes_the_same_text_to_markdown_path(tmp_path, manifest_file):
    out = tmp_path / "report.md"
    r = CliRunner().invoke(cli_mod.app, ["run", str(manifest_file), "--markdown", str(out)])
    assert r.exit_code == 0, r.output
    assert f"crosswalk written to {out}" in r.output
    assert _stable(out.read_text(encoding="utf-8")) == _stable(render_markdown(evaluate(resolved_manifest())))


def test_the_cli_without_markdown_prints_the_json_report(manifest_file):
    r = CliRunner().invoke(cli_mod.app, ["run", str(manifest_file)])
    assert r.exit_code == 0, r.output
    assert '"manifest_valid": true' in r.output
