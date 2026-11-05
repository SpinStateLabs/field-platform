"""C-1204: ``incident_replay.cli`` (``replay run | serve | version``), the one module no test imported.

The command functions are called directly with ``httpx.post`` replaced by a recorder, so nothing touches a network.
Every id, address and secret here is made up. The operator pair on the request is not pinned: which requests carry it is
C-1181's decision, this file pins only the perimeter secret and the request shape."""

from __future__ import annotations

import sys
import types

import pytest

typer = pytest.importorskip("typer")

from incident_replay import __version__, cli  # noqa: E402

SECRET = "made-up-shared-secret-0123456789"
SINCE, UNTIL = "2026-09-01T08:00:00Z", "2026-09-01T09:00:00Z"


class _Resp:
    def __init__(self, status=200, text="body-text"):
        self.status_code, self.text = status, text


@pytest.fixture
def post(monkeypatch):
    """Replaces ``httpx.post``; ``post.reply`` is what it returns, ``post.calls`` what it was given."""
    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        return fake.reply

    fake.reply, fake.calls = _Resp(), calls
    monkeypatch.setattr(cli.httpx, "post", fake)
    monkeypatch.delenv("FIELD_REPLAY_URL", raising=False)
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    return fake


# ---- _base ---------------------------------------------------------------------------------------------------


def test_the_base_url_defaults_to_the_local_service(monkeypatch):
    monkeypatch.delenv("FIELD_REPLAY_URL", raising=False)
    assert cli._base() == "http://127.0.0.1:8007"


def test_the_base_url_comes_from_the_environment_without_a_trailing_slash(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_URL", "http://replay.invalid:9000//")
    assert cli._base() == "http://replay.invalid:9000"


# ---- version -------------------------------------------------------------------------------------------------


def test_version_prints_the_package_version(capsys):
    cli.version()
    assert capsys.readouterr().out.strip() == f"incident-replay {__version__}"


# ---- run, JSON ---------------------------------------------------------------------------------------------


def test_run_posts_the_window_to_replay_and_prints_the_body(post, capsys):
    cli.run("agent-made-up", SINCE, UNTIL, None)
    (url, kwargs), = post.calls
    assert url == "http://127.0.0.1:8007/replay"
    assert kwargs["json"] == {"agent_id": "agent-made-up", "since": SINCE, "until": UNTIL}
    assert kwargs["timeout"] == 30.0
    assert kwargs["headers"]["x-field-auth"] == SECRET
    assert capsys.readouterr().out.strip() == "body-text"


def test_run_uses_the_service_url_from_the_environment(post, monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_URL", "http://replay.invalid:9000/")
    cli.run("agent-made-up", SINCE, UNTIL, None)
    assert post.calls[0][0] == "http://replay.invalid:9000/replay"


def test_a_non_200_from_replay_exits_one_with_the_status_and_body_on_stderr(post, capsys):
    post.reply = _Resp(422, "made-up refusal")
    with pytest.raises(typer.Exit) as caught:
        cli.run("agent-made-up", SINCE, UNTIL, None)
    assert caught.value.exit_code == 1
    out = capsys.readouterr()
    assert out.out == "" and "error 422: made-up refusal" in out.err


# ---- run, --markdown ---------------------------------------------------------------------------------------


def test_run_with_markdown_posts_to_replay_markdown_and_writes_the_file(post, tmp_path, capsys):
    post.reply = _Resp(200, "# made-up post-mortem ✓\n")
    target = tmp_path / "pm.md"
    cli.run("agent-made-up", SINCE, UNTIL, target)
    (url, kwargs), = post.calls
    assert url == "http://127.0.0.1:8007/replay/markdown"
    assert kwargs["json"] == {"agent_id": "agent-made-up", "since": SINCE, "until": UNTIL}
    assert kwargs["headers"]["x-field-auth"] == SECRET
    assert target.read_text(encoding="utf-8") == "# made-up post-mortem ✓\n"       # utf-8, not the locale
    assert capsys.readouterr().out.strip() == f"post-mortem written to {target}"


def test_a_non_200_from_replay_markdown_exits_one_and_writes_nothing(post, tmp_path, capsys):
    post.reply = _Resp(500, "made-up failure")
    target = tmp_path / "pm.md"
    with pytest.raises(typer.Exit) as caught:
        cli.run("agent-made-up", SINCE, UNTIL, target)
    assert caught.value.exit_code == 1 and not target.exists()
    assert "error 500: made-up failure" in capsys.readouterr().err


def test_run_without_markdown_never_calls_the_markdown_route(post, tmp_path):
    cli.run("agent-made-up", SINCE, UNTIL, None)
    assert [u for u, _ in post.calls] == ["http://127.0.0.1:8007/replay"]


# ---- serve ---------------------------------------------------------------------------------------------------


@pytest.fixture
def uvicorn_run(monkeypatch):
    seen = {}
    fake = types.ModuleType("uvicorn")
    fake.run = lambda app, **kwargs: seen.update(app=app, **kwargs)
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    return seen


def test_serve_runs_the_app_on_the_given_host_and_port(uvicorn_run):
    cli.serve("127.0.0.9", 8123)
    assert uvicorn_run["host"] == "127.0.0.9" and uvicorn_run["port"] == 8123
    assert uvicorn_run["app"].title


def test_serve_defaults_bind_to_loopback_8007():
    import inspect
    params = inspect.signature(cli.serve).parameters
    defaults = {n: getattr(p.default, "default", p.default) for n, p in params.items()}
    assert defaults == {"host": "127.0.0.1", "port": 8007}
