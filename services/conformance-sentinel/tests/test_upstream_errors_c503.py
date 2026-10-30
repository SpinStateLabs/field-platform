"""C-503: the sentinel's seeding and measurement code never puts another service's body in an error."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conformance_sentinel import seeded

MARK = "CANARY-8f31-zq"          # made up; stands in for a value an upstream echoes back
BIG = MARK + "x" * 5000
SRC = Path(seeded.__file__).parent


class Resp:
    def __init__(self, status: int):
        self.status_code, self.text = status, BIG

    def json(self):
        return {"token_id": "t"}


class Service:
    """A registry or delegation stub: POST answers `post_status`, PATCH and revoke answer `other_status`."""

    def __init__(self, post_status: int, other_status: int = 200):
        self.post_status, self.other_status = post_status, other_status

    def post(self, url, **kw):
        return Resp(self.other_status if url.endswith("/revoke") else self.post_status)

    def patch(self, url, **kw):
        return Resp(self.other_status)


def test_a_failed_seed_mint_names_the_status_only(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        seeded.provision(Service(201), Service(500), tmp_path, wait=lambda s: None)
    assert str(exc.value) == "mint returned 500"


def test_a_failed_seed_revoke_names_the_status_only(tmp_path):
    class Delegation(Service):
        def post(self, url, **kw):
            return Resp(404 if url.endswith("/revoke") else 201)

    with pytest.raises(RuntimeError) as exc:
        seeded.provision(Service(201), Delegation(201), tmp_path, wait=lambda s: None)
    assert str(exc.value) == "revoke returned 404"


def test_a_failed_check_in_the_score_command_names_the_status_and_no_body(monkeypatch, tmp_path, caplog):
    """C-642 (reviewer C-584 F-C584-2): the sentinel `score` command's /check measurement is driven with a stub
    sentinel that answers /check 500 with a marker plus 5,000 characters; the refusal line names the status only.
    (This replaces a regex over f-strings, which a concatenation or an `error ` prefix slipped past.)"""
    import logging

    from typer.testing import CliRunner

    from conformance_sentinel import cli

    class Stub:
        def __init__(self, *a, **kw):
            pass

        def get(self, url, **kw):
            return type("R", (), {"status_code": 200, "text": "", "json": lambda self: {"mode": "log_only", "judge": "off"}})()

        def post(self, url, **kw):
            return Resp(500)

    fixtures = seeded.Fixtures(agent_id="seed-agent", manifest_path=tmp_path / "m.yaml",
                               tokens={"expired": "t1", "active": "t2", "revoked": "t3"})
    monkeypatch.setattr(cli.httpx, "Client", Stub)
    monkeypatch.setattr(seeded, "provision", lambda **kw: fixtures)
    with caplog.at_level(logging.INFO):
        result = CliRunner().invoke(cli.app, ["score", "--manifest-dir", str(tmp_path)])
    out = result.output
    assert result.exit_code == 1, out
    assert "measurement refused: /check returned 500" in out
    assert MARK not in out and "x" * 200 not in out
    assert MARK not in caplog.text
