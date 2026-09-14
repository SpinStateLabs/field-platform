"""v1.2 D3 review fixes — every path out of ``/discover`` and ``registry scan``
either scans its input or refuses it BY NAME, and none of them quotes a value.

* D3-R1: a request that fails body validation (a typo'd field under
  ``extra='forbid'``, a wrong-typed value, a key pasted as a field NAME) is a
  422 whose errors carry ``type``/``loc``/``msg`` only — FastAPI's default
  handler quotes each error's ``input``, which is the raw secret;
* D3-R2: a CSV the csv module cannot read (a field over its 131072-character
  limit — well under the 1 MiB cap — or a bare CR inside an unquoted field)
  is a 422 / exit 2 naming the input and the line, never a 500 / traceback;
* D3-R3: an inventory row with a blank ``key_name`` is refused by line, never
  silently dropped into a 200 "scanned 0" report;
* D3-R4: a ``principals_csv`` with neither an ``owner`` nor a ``name`` column
  is refused, never silently widening nothing;
* D3-R5: a provider-prefixed key glued onto a letter or digit is still
  redacted in every string a candidate echoes.

Synthetic credentials are assembled from split literals (GitHub push
protection) and carry ``SYNTHETIC``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.discover import parse_principals, scan_api_keys, scan_service_accounts
from agent_registry.models import AgentCreate, ShadowCandidate
from agent_registry.redaction import ScanInputError
from agent_registry.store import RegistryStore

S = "SYNTHETIC"
#: The same synthetic values as test_d3_credential_scan.py (restated, not
#: imported: a test module is not an importable package under every import mode).
SYNTHETIC = {
    "anthropic": "sk-" + "ant-api03-" + (S * 5)[:40],
    "openai-style-sk": "sk-" + "proj-" + S * 3,
    "google-api-key": "AI" + "za" + (S + "0") * 3 + S[:5],
    "huggingface": "hf" + "_" + S * 4,
    "aws-access-key-id": "AK" + "IA" + S + "0000000",
    "github-token": "gh" + "p_" + S * 4,
    "slack-token": "xo" + "xb-" + "0000-" + S,
    "stripe-secret-key": "sk" + "_live_" + S * 2,
    "google-oauth-access-token": "ya" + "29." + S * 3,
    "jwt": "ey" + "J" + S + ".ey" + "J" + S + "." + S + "sig",
}
KEY = SYNTHETIC["anthropic"]
COLUMNS = "key_name,owner,service,created,last_used"
#: One field past the csv module's default field_size_limit (131072).
OVER_CSV_FIELD_LIMIT = "a" * 140_000


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    yield TestClient(create_app(store=store), raise_server_exceptions=False)
    store.close()


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "agents.sqlite3"
    store = RegistryStore(path)
    store.add(AgentCreate(agent_id="invoicing-agent", name="Invoice Drafting Copilot",
                          owner="Controller, Spin State Labs", domain="finance"))
    store.close()
    return path


def _no_value_quoted(text: str, raw: str = KEY) -> None:
    assert raw not in text
    assert raw[:12] not in text  # not even a truncated repr


# --- D3-R1: a 422 from body validation never quotes the rejected value ------------

@pytest.mark.parametrize("body, loc, error_type", [
    ({"secrets_txt": KEY}, ["body", "secrets_txt"], "extra_forbidden"),        # typo'd field
    ({"secrets_text": [KEY]}, ["body", "secrets_text"], "string_type"),        # wrong type
    ({"api_keys_csv": {"k": KEY}}, ["body", "api_keys_csv"], "string_type"),
    ({"principals_csv": 7, "secrets_text": KEY}, ["body", "principals_csv"], "string_type"),
    ({"n8n_export": KEY}, None, "dict_type"),
])
def test_discover_a_body_validation_422_never_quotes_the_value(client, body, loc, error_type):
    r = client.post("/discover", json=body)
    assert r.status_code == 422, r.text
    _no_value_quoted(r.text)
    detail = r.json()["detail"]
    assert detail and all(set(e) == {"type", "loc", "msg"} for e in detail)
    assert error_type in {e["type"] for e in detail}
    if loc is not None:
        assert loc in [e["loc"] for e in detail]


def test_discover_a_key_pasted_as_a_field_name_is_redacted_in_loc(client):
    r = client.post("/discover", json={KEY: "x", "secrets_text": "nothing"})
    assert r.status_code == 422, r.text
    _no_value_quoted(r.text)
    (err,) = r.json()["detail"]
    assert err["type"] == "extra_forbidden" and err["loc"][0] == "body"
    assert err["loc"][1].startswith("[REDACTED anthropic")


def test_agents_a_missing_field_422_does_not_quote_the_body(client):
    """Every route: pydantic's ``missing`` error quotes the WHOLE body as input."""
    r = client.post("/agents", json={"agent_id": "a", "name": "n", "domain": KEY})
    assert r.status_code == 422, r.text
    _no_value_quoted(r.text)
    assert ["body", "owner"] in [e["loc"] for e in r.json()["detail"]]


# --- D3-R2: a CSV the csv module cannot read is refused by name, never a 500 ------

@pytest.mark.parametrize("body, label, line", [
    ({"api_keys_csv": f'{COLUMNS}\n{KEY},,s,c,l\n"{OVER_CSV_FIELD_LIMIT}",o,s,c,l\n'},
     "api_keys_csv", 3),
    ({"api_keys_csv": f'"{OVER_CSV_FIELD_LIMIT}",owner,service,created,last_used\n'},
     "api_keys_csv", 1),                                              # the header itself
    ({"api_keys_csv": f"{COLUMNS}\nk\rx,o,s,c,l\n"}, "api_keys_csv", 2),  # bare CR, unquoted
    ({"accounts_csv": f'account,type\n{KEY},svc\n"{OVER_CSV_FIELD_LIMIT}",service\n'},
     "accounts_csv", 3),
    ({"secrets_text": "nothing", "principals_csv": f'owner\n"{OVER_CSV_FIELD_LIMIT}"\n'},
     "principals_csv", 2),
    # The plain reader reads `k, "a` as literal text; the unquoted-`Name, Org`
    # check's skipinitialspace reader opens a quoted field there that runs to
    # the end of the text — past the field limit, on text the first pass read.
    ({"api_keys_csv": f'{COLUMNS}\nk, "a,s,c,l\n' + "x,y,z,w,v\n" * 20_000},
     "api_keys_csv", 2),
])
def test_discover_an_unreadable_csv_is_422_by_name_and_line(client, body, label, line):
    r = client.post("/discover", json=body)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert f"{label} line {line}: unreadable CSV" in detail, detail
    _no_value_quoted(r.text)
    assert OVER_CSV_FIELD_LIMIT[:100] not in r.text


def test_scanners_raise_scan_input_error_not_csv_error():
    with pytest.raises(ScanInputError, match="api_keys_csv line 2: unreadable CSV"):
        scan_api_keys(f'{COLUMNS}\n"{OVER_CSV_FIELD_LIMIT}",o,s,c,l\n', [])
    with pytest.raises(ScanInputError, match="accounts_csv line 2: unreadable CSV"):
        scan_service_accounts(f'account,type\n"{OVER_CSV_FIELD_LIMIT}",svc\n', [])
    with pytest.raises(ScanInputError, match="principals_csv line 2: unreadable CSV"):
        parse_principals(f'owner\n"{OVER_CSV_FIELD_LIMIT}"\n')


@pytest.mark.parametrize("flag, header", [("--api-keys", COLUMNS), ("--accounts", "account,type")])
def test_cli_scan_an_unreadable_csv_exits_2_by_name(tmp_path, db, flag, header):
    big = tmp_path / "big.csv"
    big.write_text(f'{header}\n{KEY},,,,\n"{OVER_CSV_FIELD_LIMIT}",o,s,c,l\n', encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["scan", flag, str(big), "--path", str(db)])
    assert result.exit_code == 2, result.output
    assert "line 3: unreadable CSV" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    _no_value_quoted(result.output)


# --- D3-R3: a blank key_name is refused by line, never dropped --------------------

@pytest.mark.parametrize("row", [",,openai,2026,2026", ",growth@example.test,x,,", " ,,,,2026"])
def test_a_row_with_a_blank_key_name_is_refused_by_line(row):
    with pytest.raises(ScanInputError, match="api_keys_csv line 3: key_name is blank"):
        scan_api_keys(f"{COLUMNS}\nk,,x,,\n{row}\n", [])


def test_an_inventory_naming_its_keys_in_another_column_is_refused_not_scanned_empty(client):
    """``key_id`` carries the identifier, ``key_name`` is blank: the header check
    passes, so without the row check this was a 200 that scanned nothing."""
    r = client.post("/discover", json={
        "api_keys_csv": f"{COLUMNS},key_id\n,,openai,2026,2026,key-0001\n"})
    assert r.status_code == 422, r.text
    assert "api_keys_csv line 2: key_name is blank" in r.json()["detail"]


def test_cli_scan_a_blank_key_name_exits_2(tmp_path, db):
    keys = tmp_path / "blank.csv"
    keys.write_text(f"{COLUMNS}\n,,openai,2026,2026\n", encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["scan", "--api-keys", str(keys), "--path", str(db)])
    assert result.exit_code == 2, result.output
    assert "key_name is blank" in result.output


def test_a_row_of_only_blank_values_is_not_a_key_and_not_counted():
    candidates, scanned = scan_api_keys(f"{COLUMNS}\nk,,x,,\n,,,,\n , , , , \n", [])
    assert scanned == 1 and [c.identifier for c in candidates] == ["k"]


# --- D3-R4: principals_csv without an owner/name column is refused ----------------

def test_principals_without_an_owner_or_name_column_are_refused(client):
    with pytest.raises(ScanInputError, match="principals_csv header has no owner"):
        parse_principals("email\nalice\n")
    r = client.post("/discover", json={"api_keys_csv": f"{COLUMNS}\nk,alice,s,c,l\n",
                                       "principals_csv": "email\nalice\n"})
    assert r.status_code == 422, r.text
    assert "principals_csv header has no owner" in r.json()["detail"]


def test_principals_with_only_a_name_column_still_widen():
    assert parse_principals("name,aliases\nAlice,alice@example.test\n") == {
        "alice", "alice@example.test"}


# --- D3-R5: a provider-prefixed key glued onto a letter or digit is redacted ------

PROVIDER_PREFIXED = sorted(n for n in SYNTHETIC if n != "openai-style-sk")


@pytest.mark.parametrize("glue", ["prod", "9"])
@pytest.mark.parametrize("name", PROVIDER_PREFIXED)
def test_a_provider_prefixed_key_glued_onto_a_letter_or_digit_is_redacted(name, glue):
    raw = SYNTHETIC[name]
    c = ShadowCandidate(source="api-keys", identifier=glue + raw, display_name=glue + raw,
                        reason="r", evidence={"owner": f"x{raw}y"})
    dumped = c.model_dump_json()
    assert raw not in dumped
    assert c.identifier.startswith(f"{glue}[REDACTED {name} ")


def test_discover_a_glued_key_name_is_absent_from_the_response(client):
    r = client.post("/discover", json={"api_keys_csv": f"{COLUMNS}\nprod{KEY},x,s,c,l\n"})
    assert r.status_code == 200, r.text
    _no_value_quoted(r.text)
    assert r.json()["candidates"][0]["identifier"].startswith("prod[REDACTED anthropic")


def test_limit_a_broad_sk_key_glued_onto_a_letter_is_not_redacted():
    """README LIMITS pins this: the BROAD ``sk-``/``sk-proj-`` pattern keeps its
    start boundary in echoes, because ``task-``/``desk-``/``risk-`` identifiers
    end in ``sk-``. A glued ``sk-proj-`` key is echoed as is. If this starts
    failing, the limit is gone — update README LIMITS and the D3 row."""
    raw = SYNTHETIC["openai-style-sk"]
    c = ShadowCandidate(source="api-keys", identifier="prod" + raw, display_name="x", reason="r")
    assert c.identifier == "prod" + raw
