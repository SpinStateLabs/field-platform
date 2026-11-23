"""S10-9: a service-accounts CSV row with more fields than the header is a NAMED refusal, not a 500.

``csv.DictReader`` keeps the surplus fields of a long row under the key ``None`` as a list; ``scan_service_accounts`` then
called ``.strip()`` on that list (AttributeError: ``POST /discover`` answered 500 and ``registry scan --accounts`` printed a
traceback). The usual cause is an unquoted comma in a free-text notes column. The row is refused with the line number (the
wording ``api_keys_csv`` already uses), 422 over HTTP with a body that does not echo the row, exit 2 from the CLI. Extra
COLUMNS in the header are still ignored, as the README says. Every value is made up."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.discover import scan_service_accounts
from agent_registry.redaction import ScanInputError
from agent_registry.store import RegistryStore

MARK = "MARKER-6d41"
HEADER = "account,type,owner,notes"
LONG_ROW = f"svc-a,service,Bob,note,with,commas {MARK}"


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(tmp_path / "agents.sqlite3")
    yield s
    s.close()


def refused(text):
    with pytest.raises(ScanInputError) as exc:
        scan_service_accounts(text, [])
    return str(exc.value)


def test_a_row_with_more_fields_than_the_header_is_named_by_line_and_never_echoed():
    msg = refused(f"{HEADER}\n{LONG_ROW}\n")
    assert msg == "accounts_csv line 2: more fields than the header (quote any value that contains a comma)"
    assert MARK not in msg


@pytest.mark.parametrize("text,line", [
    (f"{HEADER}\nok,service,Bob,n\n{LONG_ROW}\n", 3),
    (f"{HEADER}\n{LONG_ROW}\nok,service,Bob,n\n", 2),
    (f"account,type,owner\nsvc-a,service,Bob,x,y\n", 2),
    ("account,type\nsvc-a,service,,\n", 2),
], ids=["second-data-row", "first-data-row", "three-columns", "empty-surplus-fields"])
def test_the_line_number_is_the_offending_row(text, line):
    assert f"accounts_csv line {line}:" in refused(text)


def test_a_quoted_value_with_commas_is_one_field_and_scans():
    candidates, scanned = scan_service_accounts(f'{HEADER}\nsvc-a,service,Bob,"note, with, commas"\n', [])
    assert scanned == 1 and [c.identifier for c in candidates] == ["svc-a"]


def test_a_short_row_is_still_read_not_refused():
    candidates, scanned = scan_service_accounts(f"{HEADER}\nsvc-a,service\n", [])
    assert scanned == 1 and candidates[0].identifier == "svc-a"


def test_extra_columns_in_the_header_are_still_ignored():
    text = "account,type,owner,notes,department,cost_centre\nsvc-a,service,Bob,n,Finance,42\n"
    candidates, scanned = scan_service_accounts(text, [])
    assert scanned == 1 and candidates[0].identifier == "svc-a"


def test_a_well_formed_csv_is_unchanged_by_the_check():
    text = f"{HEADER}\nsvc-a,service,Bob,n\nhuman.person,user,Alice,n\n"
    candidates, scanned = scan_service_accounts(text, [])
    assert scanned == 2 and [c.identifier for c in candidates] == ["svc-a"]


def test_a_bom_and_crlf_csv_still_scans():
    candidates, scanned = scan_service_accounts("﻿" + HEADER + "\r\nsvc-a,service,Bob,n\r\n", [])
    assert scanned == 1 and candidates[0].identifier == "svc-a"


def test_over_http_the_row_is_a_422_with_a_fixed_body_that_does_not_echo_it(store):
    client = TestClient(create_app(store=store), raise_server_exceptions=False)
    r = client.post("/discover", json={"accounts_csv": f"{HEADER}\n{LONG_ROW}\n"})
    assert r.status_code == 422
    assert r.json() == {"detail": "accounts_csv line 2: more fields than the header (quote any value that contains a comma)"}
    assert MARK not in r.text


def test_over_http_a_well_formed_csv_still_answers_200(store):
    client = TestClient(create_app(store=store))
    r = client.post("/discover", json={"accounts_csv": f"{HEADER}\nsvc-a,service,Bob,n\n"})
    assert r.status_code == 200 and r.json()["scanned_accounts"] == 1


def test_from_the_cli_the_row_is_exit_2_with_one_error_line_and_no_traceback(tmp_path):
    db = tmp_path / "agents.sqlite3"
    RegistryStore(db).close()
    csv_file = tmp_path / "accounts.csv"
    csv_file.write_text(f"{HEADER}\n{LONG_ROW}\n", encoding="utf-8")
    res = CliRunner().invoke(cli.app, ["scan", "--accounts", str(csv_file), "--path", str(db)])
    assert res.exit_code == 2
    assert res.output.strip() == ("error: accounts_csv line 2: more fields than the header "
                                  "(quote any value that contains a comma)")
    assert MARK not in res.output and "Traceback" not in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)
