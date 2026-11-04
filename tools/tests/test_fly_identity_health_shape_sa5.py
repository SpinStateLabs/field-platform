"""fly_identity_check must report, never raise, on a /health body that is not a JSON
object (scout S-A5): `null`, a list or a number decoded fine and then broke
`"_error" in h` / `h.get(...)`. Also pins the 65536-byte read cap."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fly_identity_check as fic  # noqa: E402


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _serve(monkeypatch, body: bytes):
    monkeypatch.setattr(fic.urllib.request, "urlopen", lambda url, timeout=5.0: _Resp(body))


@pytest.mark.parametrize("body", [b"null", b"[]", b"[1,2]", b"5", b'"text"', b"true", b""])
def test_a_non_object_body_is_an_error_entry_not_a_crash(monkeypatch, body):
    _serve(monkeypatch, body)
    out = fic._health("http://127.0.0.1:1")
    assert set(out) == set(fic.HEALTH_PREFIX)
    assert all(isinstance(v, dict) and "_error" in v for v in out.values())


def test_a_non_object_body_makes_check_health_report_a_problem(monkeypatch):
    _serve(monkeypatch, b"[]")
    problems = fic.check_health(fic._health("http://127.0.0.1:1"), "none")
    assert len(problems) == len(fic.HEALTH_PREFIX)
    assert all("unreadable" in p for p in problems)


@pytest.mark.parametrize("bad", [None, [], 5, "x"])
def test_check_health_itself_survives_a_non_dict_entry(bad):
    problems = fic.check_health({"ledger": bad}, "none")
    assert problems and "ledger" in problems[0]


def test_an_object_body_still_passes_through():
    ok = {s: {"operator_identity_id": None, "identity_present": False} for s in fic.HEALTH_PREFIX}
    assert fic.check_health(ok, "none") == []


def test_the_read_is_capped_at_65536_bytes(monkeypatch):
    big = json.dumps({"operator_identity_id": None, "identity_present": False,
                      "pad": "x" * 70000}).encode()
    assert len(big) > 65536
    _serve(monkeypatch, big)
    out = fic._health("http://127.0.0.1:1")
    # truncated at the cap, so it is not valid JSON: reported as an error, not parsed
    assert all("_error" in v for v in out.values())


def test_a_body_exactly_under_the_cap_parses(monkeypatch):
    body = json.dumps({"operator_identity_id": None, "identity_present": False}).encode()
    _serve(monkeypatch, body)
    assert all(v.get("identity_present") is False for v in fic._health("http://127.0.0.1:1").values())
