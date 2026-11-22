"""S7-11: csv.Error is not a ValueError, so a roster the csv module cannot read escaped every caller that catches
ValueError (the CLI sweep, api._resolve_roster, SweepRequest handling), and POST /sweep's roster_csv had no size cap.

Three shapes: a field over the csv module's 131072-character limit; a bare CR inside an unquoted field; and a `k, "a...`
row that the plain reader splits into small fields but the skipinitialspace reader reads as ONE quoted field running
past the limit (the second reader of the spaced-comma check). Each is a named refusal at parse_roster_entries, a 422 at
POST /sweep with the roster in the body, and an `error:` line (not a traceback) at the CLI sweep. The message holds the
line number and csv.Error's own text, never a field's content."""

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from lifecycle_manager.api import ROSTER_CSV_MAX_CHARS, create_app
from lifecycle_manager.engine import UnreadableRoster, parse_roster, parse_roster_entries

from test_roster_aliases import FakeRegistry, NoTokens, RecordingLedger, _patch_cli_clients, agent

SECRET = "SENTINEL-FIELD-CONTENT"
BIG = "owner,aliases\nDon," + SECRET + "a" * 200_000 + "\n"
BARE_CR = "owner,aliases\nDon,Alias" + "\r" + SECRET + "x\n"
SECOND_READER = "owner,aliases\nk, \"" + "a," * 70_000

CASES = {"big-field": (BIG, 2), "bare-cr": (BARE_CR, 2), "second-reader": (SECOND_READER, 2)}


@pytest.mark.parametrize("text, line", list(CASES.values()), ids=list(CASES))
def test_an_unreadable_csv_is_a_named_value_error_at_parse_roster_entries(text, line):
    for parse in (parse_roster_entries, parse_roster):
        with pytest.raises(UnreadableRoster) as exc:
            parse(text)
        assert isinstance(exc.value, ValueError)
        assert f"owners.csv line {line}: unreadable CSV (" in str(exc.value)
        assert SECRET not in str(exc.value)


def test_a_readable_roster_still_parses():
    assert [e.owner for e in parse_roster_entries("owner,aliases\nDon Hagell,Don\n")] == ["Don Hagell"]


@pytest.mark.parametrize("text", [c[0] for c in CASES.values()], ids=list(CASES))
def test_post_sweep_with_an_unreadable_roster_in_the_body_is_422(tmp_path, monkeypatch, text):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    served = create_app(registry=FakeRegistry([agent("a", "Verifier")]), delegation=NoTokens(),
                        ledger=RecordingLedger(), every=0)
    r = TestClient(served, raise_server_exceptions=False).post("/sweep", json={"roster_csv": text})
    assert r.status_code == 422 and "unreadable CSV" in r.json()["detail"]
    assert SECRET not in r.text


# a bare CR cannot reach the CLI as one: Path.read_text translates it to a newline, so it is a plain row there
@pytest.mark.parametrize("text", [BIG, SECOND_READER], ids=["big-field", "second-reader"])
def test_the_cli_sweep_prints_an_error_line_not_a_traceback(tmp_path, monkeypatch, text):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_bytes(text.encode("utf-8"))
    ledger = _patch_cli_clients(monkeypatch, [agent("a", "Verifier")])
    result = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)          # a clean exit, not a propagated exception
    assert "error: owners.csv line" in result.output and "unreadable CSV" in result.output
    assert SECRET not in result.output
    assert ledger.events == []


def test_a_roster_csv_over_one_mebibyte_is_422_and_exactly_one_is_not_refused_for_size(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    served = create_app(registry=FakeRegistry([agent("a", "Verifier")]), delegation=NoTokens(),
                        ledger=RecordingLedger(), every=0)
    client = TestClient(served, raise_server_exceptions=False)
    over = "owner\nDon\n" + "x" * (ROSTER_CSV_MAX_CHARS - len("owner\nDon\n") + 1)
    assert len(over) == ROSTER_CSV_MAX_CHARS + 1
    assert client.post("/sweep", json={"roster_csv": over}).status_code == 422
    exact = over[:-1]
    assert len(exact) == ROSTER_CSV_MAX_CHARS
    r = client.post("/sweep", json={"roster_csv": exact})
    assert r.status_code != 422 or "at most" not in r.text      # the size rule does not fire at the cap
