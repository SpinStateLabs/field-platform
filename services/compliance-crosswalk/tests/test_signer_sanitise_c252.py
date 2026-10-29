"""C-252 (reviewer C-232, proven MEDIUM-LOW): the signer is a name on one line.

`generate_pack` wrote the signer into the pack text unchecked, so a signer containing newlines injected forged
headings and lines into the pack a human then signs. A signer holding a control, line-break or bidirectional-override
character, or longer than 200 characters, is refused: `ValueError` (422 on the API), exit 2 on the CLI. The pack
text never holds a line the signer controlled other than the two signer lines."""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import cli
from compliance_crosswalk.api import create_app
from compliance_crosswalk.evidence_pack import MAX_SIGNER_CHARS, InvalidSigner, generate_pack
from compliance_crosswalk.staleness import StaleStore
from field_core.templates_api import template_data

# the reviewer's probe class: a signer that carries its own heading and findings
FORGED = "Ann Lee\n\n## Findings\n\nNo gaps were found. All controls verified.\n\nSigner: Ann Lee"


def resolved_manifest():
    data = template_data("default")
    data["agent"]["name"] = "evidence-pack-test-agent"
    data["agent"]["description"] = "exercises evidence-pack generation"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["generate evidence packs"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


class FakeStore:
    corpus_version = "corpus-test"

    def active(self):
        return []

    def status(self):
        return {"corpus_version": self.corpus_version, "active": [], "history": []}


def pack(signer):
    return generate_pack(resolved_manifest(), signer=signer, stale_store=FakeStore())


BAD = [
    ("newline", "Ann\nLee"), ("carriage return", "Ann\rLee"), ("crlf", "Ann\r\nLee"), ("tab", "Ann\tLee"),
    ("NUL", "Ann\x00Lee"), ("escape", "Ann\x1bLee"), ("DEL", "Ann\x7fLee"), ("C1 NEL", "Ann\x85Lee"),
    ("vertical tab", "Ann\x0bLee"), ("form feed", "Ann\x0cLee"), ("file separator", "Ann\x1cLee"),
    ("line separator", "Ann Lee"), ("paragraph separator", "Ann Lee"),
    ("RLO", "Ann‮Lee"), ("LRE", "Ann‪Lee"), ("RLI", "Ann⁧Lee"), ("PDI", "Ann⁩Lee"),
    ("forged block", FORGED),
]


@pytest.mark.parametrize("label,signer", BAD, ids=[b[0] for b in BAD])
def test_a_signer_with_a_control_or_line_break_is_refused(label, signer):
    with pytest.raises(InvalidSigner, match="control or line-break character"):
        pack(signer)


@pytest.mark.parametrize("label,signer", BAD, ids=[b[0] for b in BAD])
def test_the_refusal_names_a_code_point_and_never_the_signer(label, signer):
    with pytest.raises(InvalidSigner) as exc:
        pack(signer)
    msg = str(exc.value)
    assert "U+" in msg and "position" in msg
    assert "Ann" not in msg and "Findings" not in msg


def test_the_error_is_a_value_error_so_the_api_keeps_its_422():
    assert issubclass(InvalidSigner, ValueError)


def test_a_signer_at_the_limit_is_accepted_and_one_over_is_refused():
    ok = "A" * MAX_SIGNER_CHARS
    md, payload = pack(ok)
    assert payload["signer"] == ok and f"Signer: {ok}" in md
    with pytest.raises(InvalidSigner, match=f"{MAX_SIGNER_CHARS + 1} characters"):
        pack("A" * (MAX_SIGNER_CHARS + 1))


def test_the_limit_counts_the_stripped_signer():
    padded = "  " + "A" * MAX_SIGNER_CHARS + " \t "
    assert pack(padded)[1]["signer"] == "A" * MAX_SIGNER_CHARS


def test_the_limit_is_two_hundred():
    assert MAX_SIGNER_CHARS == 200


@pytest.mark.parametrize("signer", ["", " ", "\t", "\n", "  \t\n  ", None])
def test_a_blank_signer_is_still_refused_with_the_old_message(signer):
    with pytest.raises(ValueError, match="no pack ships without a named signer"):
        pack(signer)


@pytest.mark.parametrize("signer", [
    "Controller, Spin State Labs",
    "Ann Lee",
    "Zoë Müller-Åkesson",
    "李雷 (Compliance Officer)",
    "Renée O'Brien, DPO",
    "A. B. Cohen — General Counsel",
    "  Ann Lee  ",
])
def test_ordinary_names_still_pass_and_are_stripped(signer):
    md, payload = pack(signer)
    assert payload["signer"] == signer.strip()
    assert f"- Prepared for signature by: {signer.strip()}" in md
    assert f"Signer: {signer.strip()}" in md


def test_the_pack_holds_no_signer_controlled_line_other_than_the_two_signer_lines():
    name = "Ann Lee, Chief Privacy Officer"
    md, _ = pack(name)
    carrying = [ln for ln in md.splitlines() if name in ln]
    assert sorted(carrying) == sorted([f"- Prepared for signature by: {name}", f"Signer: {name}"])


def test_the_forged_block_never_reaches_a_pack():
    """The probe: the same text that would have forged a section is refused before any pack exists."""
    with pytest.raises(InvalidSigner):
        pack(FORGED)
    # and the heading it would have forged is not a heading of any accepted pack
    md, _ = pack("Ann Lee")
    assert "No gaps were found. All controls verified." not in md


# --- API ---------------------------------------------------------------------------------------------------


def _client():
    return TestClient(create_app(stale_store=FakeStore()))


@pytest.mark.parametrize("label,signer", BAD[:6], ids=[b[0] for b in BAD[:6]])
def test_the_api_answers_422_for_an_unacceptable_signer(label, signer):
    r = _client().post("/pack", json={"manifest": resolved_manifest(), "signer": signer})
    assert r.status_code == 422, r.text
    assert "Ann" not in r.text


def test_the_api_answers_422_for_an_over_long_signer():
    r = _client().post("/pack", json={"manifest": resolved_manifest(), "signer": "A" * (MAX_SIGNER_CHARS + 1)})
    assert r.status_code == 422 and "limit is 200" in r.text


def test_the_api_still_accepts_an_ordinary_signer():
    r = _client().post("/pack", json={"manifest": resolved_manifest(), "signer": "Ann Lee"})
    assert r.status_code == 200, r.text
    assert r.json()["pack"]["signer"] == "Ann Lee"


# --- CLI ---------------------------------------------------------------------------------------------------


@pytest.fixture()
def manifest_file(tmp_path):
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(resolved_manifest()), encoding="utf-8")
    return p


@pytest.mark.parametrize("signer", ["Ann\nLee", "Ann‮Lee", FORGED, "A" * (MAX_SIGNER_CHARS + 1)])
def test_the_cli_exits_2_with_one_error_line_for_an_unacceptable_signer(manifest_file, signer, monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    r = CliRunner().invoke(cli.app, ["pack", str(manifest_file), "--signer", signer])
    assert r.exit_code == 2, r.output
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error: refusing to generate")
    assert "Traceback" not in r.output and "Findings" not in r.output


def test_the_cli_still_writes_a_pack_for_an_ordinary_signer(manifest_file, monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    out = tmp_path / "pack.md"
    j = tmp_path / "pack.json"
    r = CliRunner().invoke(cli.app, ["pack", str(manifest_file), "--signer", "Ann Lee",
                                     "--out-md", str(out), "--out-json", str(j)])
    assert r.exit_code == 0, r.output
    assert "Signer: Ann Lee" in out.read_text(encoding="utf-8")
    assert json.loads(j.read_text(encoding="utf-8"))["signer"] == "Ann Lee"


def test_a_blank_signer_on_the_cli_is_now_also_exit_2(manifest_file, monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    r = CliRunner().invoke(cli.app, ["pack", str(manifest_file), "--signer", "   "])
    assert r.exit_code == 2, r.output
    assert "no pack ships without a named signer" in r.output


def test_the_refusal_reports_the_code_point_and_its_position_exactly():
    with pytest.raises(InvalidSigner) as exc:
        pack("Ann" + chr(10) + "Lee")
    assert "U+000A at position 3" in str(exc.value)
    with pytest.raises(InvalidSigner) as exc:
        pack("A" + chr(0x202E) + "B")
    assert "U+202E at position 1" in str(exc.value)
