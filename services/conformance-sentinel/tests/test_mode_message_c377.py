"""C-377 (reviewer C-374 F-C374-1, F-C374-4): the refusal never echoes the value, and `sentinel serve` turns it
into one line and exit 2 (a configuration error) instead of a traceback.

The value of FIELD_SENTINEL_MODE might be a secret an operator pointed the variable at by mistake
(`FIELD_SENTINEL_MODE=$SOME_KEY`): none of it may reach the exception text, its repr, the traceback or the CLI output."""

from __future__ import annotations

import traceback

import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli
from conformance_sentinel.mode import InvalidSentinelMode, resolve_mode

ENV = "FIELD_SENTINEL_MODE"
# secret-shaped, and chosen so that no 4-character slice of it occurs in the accepted-values wording
CANARY = "Zq9#Wv7!Kx2$Pm4@Lt8%Jb5^Hd3&Rc6*Yn1(Gf0)"


def _slices(value: str, n: int = 4):
    low = value.lower()
    return {low[i:i + n] for i in range(len(low) - n + 1)}


def test_the_canary_shares_no_four_character_slice_with_the_wording():
    """The canary check below is only meaningful if the fixed wording cannot contain a slice of it by accident."""
    monkey_msg = "FIELD_SENTINEL_MODE is set to an unrecognised value (41 characters); use log_only or enforce " \
                 "(or leave it unset for log_only)"
    assert not any(s in monkey_msg.lower() for s in _slices(CANARY))


def test_no_part_of_the_value_reaches_the_message_the_repr_or_the_traceback(monkeypatch):
    monkeypatch.setenv(ENV, CANARY)
    with pytest.raises(InvalidSentinelMode) as exc:
        resolve_mode()
    text = "\n".join([str(exc.value), repr(exc.value), repr(exc.value.args),
                      "".join(traceback.format_exception(exc.value))]).lower()
    leaked = [s for s in _slices(CANARY) if s in text]
    assert not leaked, leaked
    assert f"({len(CANARY)} characters)" in str(exc.value)


@pytest.mark.parametrize("raw", ["enfroce", "on", "true", "1", "off", "observe", CANARY, "x" * 300])
def test_no_four_character_slice_of_any_unrecognised_value_is_echoed(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    with pytest.raises(InvalidSentinelMode) as exc:
        resolve_mode()
    msg = str(exc.value).lower()
    wording_free = {s for s in _slices(raw) if s not in "log_only enforce unrecognised characters value"}
    assert not [s for s in wording_free if s in msg]


# --- the command -----------------------------------------------------------------------------------------


def _serve(monkeypatch, raw=None):
    ran = []
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: ran.append((app, kw)))
    if raw is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, raw)
    r = CliRunner().invoke(cli.app, ["serve", "--port", "18999"])
    return r, ran


@pytest.mark.parametrize("raw", ["enfroce", "on", "1", CANARY])
def test_serve_refuses_with_one_error_line_and_exit_2_and_binds_nothing(monkeypatch, raw):
    r, ran = _serve(monkeypatch, raw)
    assert r.exit_code == 2, r.output
    assert ran == []                                           # uvicorn never started
    lines = [ln for ln in (r.output or "").splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error: FIELD_SENTINEL_MODE")
    assert "Traceback" not in r.output
    assert not [s for s in _slices(raw) if s in r.output.lower() and s not in "log_only enforce unrecognised characters value"]


@pytest.mark.parametrize("raw", [None, "", "log-only", "enforce", " Enforced "])
def test_serve_still_starts_for_every_valid_or_blank_value(monkeypatch, raw):
    r, ran = _serve(monkeypatch, raw)
    assert r.exit_code == 0, r.output
    assert len(ran) == 1 and ran[0][1]["port"] == 18999
