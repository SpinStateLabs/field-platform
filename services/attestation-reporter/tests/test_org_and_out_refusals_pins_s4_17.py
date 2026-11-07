"""S4-17 follow-up: pins for the survivors Lane O measured on PR 665 (the literal limit, stripped length, positions,
inner spacing, the API detail text, the exact CLI refusal forms, and the texts-built-first ordering)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from attestation_reporter import api as api_mod
from attestation_reporter import cli as cli_mod
from attestation_reporter import render as render_mod
from attestation_reporter.api import create_app
from attestation_reporter.engine import PackEngine
from attestation_reporter.org import MAX_ORG_CHARS, InvalidOrg, checked_org
from field_core.authn import ENV_VAR


def test_the_limit_is_exactly_200_characters():
    assert MAX_ORG_CHARS == 200
    assert checked_org("o" * 200) == "o" * 200
    with pytest.raises(InvalidOrg):
        checked_org("o" * 201)


def test_the_limit_is_measured_after_the_strip():
    padded = "   " + "o" * 200 + "   "
    assert checked_org(padded) == "o" * 200
    with pytest.raises(InvalidOrg):
        checked_org("   " + "o" * 201 + "   ")


def test_the_reported_position_is_in_the_stripped_name_and_names_the_code_point():
    with pytest.raises(InvalidOrg) as info:
        checked_org("   Ac\nme")                      # stripped: "Ac\nme", the newline is at position 2
    msg = str(info.value)
    assert "U+000A at position 2" in msg, msg
    with pytest.raises(InvalidOrg) as info:
        checked_org("Acme​Corp")                 # U+200B at position 4
    assert "U+200B at position 4" in str(info.value)


def test_inner_spacing_is_kept_as_typed():
    assert checked_org("Acme  Corp") == "Acme  Corp"
    assert checked_org("  Acme   Corp  ") == "Acme   Corp"


def test_the_refusal_texts_are_fixed_forms():
    with pytest.raises(InvalidOrg) as blank:
        checked_org("  ")
    assert str(blank.value) == "the org must be non-blank text"
    with pytest.raises(InvalidOrg) as long:
        checked_org("o" * 201)
    assert str(long.value) == "the org is 201 characters; the limit is 200"


def test_the_api_detail_is_the_fixed_text(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    c = TestClient(create_app(engine=PackEngine()), raise_server_exceptions=False)
    r = c.get("/pack", params={"org": "   "})
    assert r.status_code == 422 and r.json() == {"detail": "the org must be non-blank text"}
    r = c.get("/pack.html", params={"org": "o" * 201})
    assert r.status_code == 422 and r.json() == {"detail": "the org is 201 characters; the limit is 200"}


@pytest.fixture()
def cli(monkeypatch):
    monkeypatch.setattr(api_mod, "engine_from_env", lambda org="Spin State Labs": PackEngine(org=org))
    runner = CliRunner()
    return lambda *args: runner.invoke(cli_mod.app, ["render", "--no-pdf", *args])


def test_the_out_refusal_names_the_exception_type_only(cli, tmp_path):
    f = tmp_path / "private-dir-name-XYZ" / "afile"
    f.parent.mkdir()
    f.write_text("x", encoding="utf-8")
    r = cli("--out", str(f))
    assert r.exit_code == 2, r.output
    assert re.search(r"refused: --out is not a usable directory \(\w+Error\)", r.output), r.output
    assert "private-dir-name-XYZ" not in r.output and str(tmp_path) not in r.output


def test_the_write_failure_refusal_names_the_exception_type_only(cli, tmp_path):
    out = tmp_path / "private-dir-name-XYZ"
    (out / "board-pack.json").mkdir(parents=True)
    r = cli("--out", str(out))
    assert r.exit_code == 2, r.output
    assert re.search(r"refused: cannot write the pack into --out \(\w+Error\)", r.output), r.output
    assert "private-dir-name-XYZ" not in r.output and str(tmp_path) not in r.output


def test_both_texts_are_built_before_anything_is_written(cli, tmp_path, monkeypatch):
    def boom(pack):
        raise OSError(f"disk full at {tmp_path}")

    monkeypatch.setattr(render_mod, "render_html", boom)
    out = tmp_path / "o"
    r = cli("--out", str(out))
    assert r.exit_code == 2, r.output
    assert "cannot write the pack into --out (OSError)" in r.output and str(tmp_path) not in r.output
    assert not (out / "board-pack.json").exists() and not (out / "board-pack.html").exists()
