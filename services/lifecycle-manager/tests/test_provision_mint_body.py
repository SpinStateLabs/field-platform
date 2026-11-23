"""S10-13: a delegation 201 whose body is not a JSON object must not crash `provision`.

The agent is already registered and capped when step 5 runs, so a traceback from the mint step loses the
whole report (and the token id the CLI would print). The mint step records a failed step and returns the
report instead; the non-201 path is unchanged."""

from __future__ import annotations

import pytest

from test_provision_rate_limits import DECLARED, GRANTOR, Stack, _manifest  # noqa: F401  (fixtures reused)
from test_provision_rate_limits import stack  # noqa: F401  (pytest fixture)


class _Answer:
    """A delegation reply: 201, with a body the caller chooses."""

    status_code = 201
    text = "not json"

    def __init__(self, kind):
        self.kind = kind

    def json(self):
        if self.kind == "text":
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return {"list": [], "null": None, "number": 7, "string": "ok"}[self.kind]


class _MintAnswers:
    """Delegation client that forwards everything except POST /tokens."""

    def __init__(self, real, kind):
        self.real, self.kind = real, kind

    def post(self, path, **kw):
        if path == "/tokens":
            return _Answer(self.kind)
        return self.real.post(path, **kw)

    def get(self, path, **kw):
        return self.real.get(path, **kw)

    def put(self, path, **kw):
        return self.real.put(path, **kw)


@pytest.mark.parametrize("kind", ["text", "list", "null", "number", "string"])
def test_an_unusable_201_mint_body_returns_a_failed_mint_step_not_a_traceback(stack, tmp_path, kind):
    stack.engine.delegation = _MintAnswers(stack.delegation, kind)
    report = stack.provision(_manifest(tmp_path, "m.yaml", DECLARED))
    assert report.ok is False
    assert report.token_id is None and report.expires_at is None
    assert [(s.step, s.outcome) for s in report.steps] == [
        ("validate", "ok"), ("register", "ok"), ("cap", "ok"), ("rate_limits", "ok"), ("mint", "failed")]
    mint = report.steps[-1]
    assert mint.http_status == 201
    assert "delegation answered 201 but its body was not a JSON object" in mint.detail
    assert "list tokens for the agent before retrying" in mint.detail


def test_a_well_formed_201_still_mints(stack, tmp_path):
    report = stack.provision(_manifest(tmp_path, "m.yaml"))
    assert report.ok is True and report.token_id
    assert report.steps[-1].step == "mint" and report.steps[-1].outcome == "ok"


def test_a_non_201_mint_answer_is_unchanged(stack, tmp_path):
    class Refuse(_MintAnswers):
        def post(self, path, **kw):
            if path == "/tokens":
                a = _Answer("text")
                a.status_code, a.text = 403, "refused: no"
                return a
            return self.real.post(path, **kw)

    stack.engine.delegation = Refuse(stack.delegation, "text")
    report = stack.provision(_manifest(tmp_path, "m.yaml"))
    assert report.ok is False
    assert report.steps[-1].step == "mint" and report.steps[-1].http_status == 403
    assert "refused: no" in report.steps[-1].detail
