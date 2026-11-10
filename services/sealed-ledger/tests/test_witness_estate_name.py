"""S12-23: --estate is a checked name, not any non-blank text.

`witness run` stored the UNstripped text in the signed anchor.remote payload, while `verify-witness --estate` selects by
exact equality, so an estate saved as 'gb10 ' (or with a tab, newline, zero-width or bidi character, or at any length)
was witnessed under a name no later `verify-witness --estate gb10` finds ('nothing witnessed'). One shared checker
(witness.checked_estate) is used by Witness, `witness run` and `verify-witness`: 1..64 characters, no whitespace and no
control / format / line / paragraph-separator character anywhere. A bad name is a usage error (exit 2, fixed text that
does not echo the value), never 'nothing witnessed'."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from sealed_ledger import witness as w
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore
from test_witness import FLY, OBSERVED, StubFly, env, local, served  # noqa: F401 (fixtures)

runner = CliRunner()

BAD = [
    " gb10", "gb10 ", "gb10\n", "gb10\t", "g b10", "gb10\r\n",
    "g​b10",      # zero-width space (Cf)
    "gb10‮",      # right-to-left override (Cf, bidi)
    "gb‎10",      # left-to-right mark (Cf)
    "gb\x0010", "gb10\x7f",          # Cc
    "gb10 ", "gb10 ",      # Zl / Zp
    "gb10 ", "gb10　",      # no-break and ideographic space
    "", "   ", "x" * 65,
]
GOOD = ["gb10", "fly", "estate-2", "Estate_3.eu", "x" * 64, "é1"]


@pytest.mark.parametrize("name", GOOD)
def test_a_plain_name_is_accepted_unchanged(name):
    assert w.checked_estate(name) == name


@pytest.mark.parametrize("name", BAD, ids=repr)
def test_a_bad_name_is_refused_with_fixed_text(name):
    with pytest.raises(ValueError) as exc:
        w.checked_estate(name)
    assert str(exc.value) == w.ESTATE_NAME_REFUSAL
    assert name.strip() not in str(exc.value) or name.strip() == ""


def test_a_non_string_is_refused():
    for bad in (None, 7, b"gb10"):
        with pytest.raises(ValueError):
            w.checked_estate(bad)  # type: ignore[arg-type]


def _witness(estate, url, stub):
    return w.Witness(local_estate=estate, fly_url=FLY, fly=w.build_fly_client(transport=httpx.MockTransport(stub)),
                     ledger=w.build_ledger_client(url), observer=w.observer_record("2026-09-13T11:00:00+00:00"),
                     clock=lambda: OBSERVED)


@pytest.mark.parametrize("name", ["g​b10", " gb10", "x" * 65])
def test_a_witness_with_a_bad_estate_cannot_be_built(name):
    with pytest.raises(ValueError):
        w.Witness(local_estate=name, fly_url=FLY, fly=None, ledger=None, observer={})  # type: ignore[arg-type]


def test_a_checked_estate_other_than_gb10_still_ticks(env, local):  # noqa: F811
    store, url = local
    stub = StubFly()
    outcome = _witness("estate-2", url, stub).tick()
    assert outcome.direction1 == "appended"
    assert LedgerStore(store.path).events(event_type="anchor.remote")[-1].payload["estate"] == "fly"


@pytest.mark.parametrize("name", BAD, ids=repr)
def test_witness_run_refuses_a_bad_estate_with_exit_2_and_appends_nothing(env, local, name):  # noqa: F811
    store, _ = local
    before = len(LedgerStore(store.path).events())
    res = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", name, "--fly-url", FLY])
    assert res.exit_code == 2
    assert w.ESTATE_NAME_REFUSAL in res.output
    assert len(LedgerStore(store.path).events()) == before


@pytest.mark.parametrize("name", BAD, ids=repr)
def test_verify_witness_refuses_a_bad_estate_with_exit_2(tmp_path, name):
    res = runner.invoke(cli_app, ["verify-witness", "--estate", name, "--events-file", str(tmp_path / "e.json"),
                                  "--path", str(tmp_path / "events.jsonl")])
    assert res.exit_code == 2
    assert w.ESTATE_NAME_REFUSAL in res.output
    assert "nothing witnessed" not in res.output


def test_verify_witness_still_accepts_a_plain_name(tmp_path):
    src = tmp_path / "e.json"
    src.write_text("[]", encoding="utf-8")
    res = runner.invoke(cli_app, ["verify-witness", "--estate", "gb10", "--events-file", str(src),
                                  "--path", str(tmp_path / "events.jsonl")])
    assert w.ESTATE_NAME_REFUSAL not in res.output
