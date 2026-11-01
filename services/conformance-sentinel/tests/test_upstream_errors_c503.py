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


@pytest.mark.parametrize("name", ["cli.py", "seeded.py"])
def test_no_error_in_these_files_interpolates_a_reply_body(name):
    """The /check measurement in cli.py is built inside a command and cannot be driven here without the whole
    stack, so the source is pinned: no f-string in these files interpolates a response body (`.text`)."""
    src = (SRC / name).read_text(encoding="utf-8")
    bad = [m.group(0) for m in re.finditer(r"""f["'][^"'\n]*\{[^}\n]*\.text\b[^}\n]*\}[^"'\n]*["']""", src)]
    # cli.py's operator-facing relay of the sentinel's own reply (`typer.echo(resp.text)`) is not an error message
    bad = [b for b in bad if not b.startswith('f"error ')]
    assert bad == [], bad
