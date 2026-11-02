"""renew_token ledger helpers (C-1042, reviewer C-215 F-C215-1/-2/-3): pins for the repo-path fallback
(`add_repo_field_core`), the load-once signer (`caller_signer`) and the messages that name an exception
class and never its text. Tests only: no estate, no network. The key, the identity and the exception text
are made-up constants; field_core is stubbed in sys.modules so no real key is ever read.

The repo-path fallback is run from a COPY of the tool beside a fake `packages/field-core/src`, in a child
interpreter where `find_spec("field_core")` is stubbed, so the real checkout is never touched."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import renew_token  # noqa: E402

CANARY = "zq7kx9m2wd"
SLICES = [CANARY[i:i + 4] for i in range(len(CANARY) - 3)]
IDENT, KEY = "svc-test-caller", "made-up-key-material-1"

CHILD = r"""
import importlib.util, json, sys
tool, importable = sys.argv[1], sys.argv[2] == "1"
real = importlib.util.find_spec
importlib.util.find_spec = lambda name, *a, **k: (object() if importable else None) if name == "field_core" else real(name, *a, **k)
spec = importlib.util.spec_from_file_location("rt_copy", tool)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
before = list(sys.path)
mod.Renewal.add_repo_field_core()
first = list(sys.path)
mod.Renewal.add_repo_field_core()
print(json.dumps({"before": before, "first": first, "second": list(sys.path)}))
"""


def run_copy(tmp_path: Path, *, importable: bool, make_src: bool = True, decoys: bool = True) -> dict:
    """Run a copy of renew_token.py at <tmp>/tools/ and report sys.path around add_repo_field_core."""
    (tmp_path / "tools").mkdir()
    tool = tmp_path / "tools" / "renew_token.py"
    shutil.copy(TOOLS / "renew_token.py", tool)
    src = tmp_path / "packages" / "field-core" / "src"
    if make_src:
        src.mkdir(parents=True)
    if decoys:  # a wrong root (one dirname too few or too many) must not find these
        (tmp_path / "tools" / "packages" / "field-core" / "src").mkdir(parents=True)
        (tmp_path.parent / "packages" / "field-core" / "src").mkdir(parents=True, exist_ok=True)
    done = subprocess.run([sys.executable, "-c", CHILD, str(tool), "1" if importable else "0"], cwd=tmp_path,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    out["src"] = str(src)
    out["decoys"] = [str(tmp_path / "tools" / "packages" / "field-core" / "src"),
                     str(tmp_path.parent / "packages" / "field-core" / "src")]
    return out


# --- F-C215-1: the repo-path fallback ------------------------------------------------------------


def test_the_repo_copy_is_appended_never_prepended_when_field_core_is_not_installed(tmp_path):
    seen = run_copy(tmp_path, importable=False)
    assert seen["first"][-1] == seen["src"], "the repo copy was not appended last"
    assert seen["first"][:-1] == seen["before"], "an existing entry moved: the repo copy must not be prepended"
    assert seen["first"].index(seen["src"]) != 0


def test_an_installed_field_core_means_the_path_is_left_alone(tmp_path):
    seen = run_copy(tmp_path, importable=True)
    assert seen["first"] == seen["before"]
    assert seen["src"] not in seen["second"]


def test_a_missing_source_directory_adds_nothing(tmp_path):
    seen = run_copy(tmp_path, importable=False, make_src=False)
    assert seen["first"] == seen["before"] and seen["second"] == seen["before"]


def test_the_root_is_the_checkout_beside_tools_and_no_decoy_is_used(tmp_path):
    seen = run_copy(tmp_path, importable=False)
    assert seen["src"] in seen["first"]
    for decoy in seen["decoys"]:
        assert decoy not in seen["first"], "a directory above or below the checkout was added"


def test_the_repo_copy_is_added_once_across_two_calls(tmp_path):
    seen = run_copy(tmp_path, importable=False)
    assert seen["second"].count(seen["src"]) == 1
    assert seen["second"] == seen["first"]


# --- F-C215-2/-3: the signer and the messages --------------------------------------------------------


class FakeApi:
    def __init__(self, status: int = 201):
        self.status, self.calls = status, []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        return self.status, {}


def bare(status: int = 201) -> renew_token.Renewal:
    """A Renewal with only what the ledger path reads (no store, no journal, no network)."""
    run = object.__new__(renew_token.Renewal)
    run.a = SimpleNamespace(agent="canary-agent")
    run.secret = None
    run.api = FakeApi(status)
    return run


@pytest.fixture()
def fake_field_core(monkeypatch):
    """field_core.clients stubbed: CallerSigner.from_env counts its calls; behaviour is set per test."""
    state = SimpleNamespace(loads=0, raises=None, returns="signer-object", sign_raises=None)

    class CallerSigner:
        @classmethod
        def from_env(cls):
            state.loads += 1
            if state.raises is not None:
                raise state.raises
            return state.returns

    def signed_append_body(signer, event_type, payload, agent, sent):
        if state.sign_raises is not None:
            raise state.sign_raises
        return {"event_type": event_type, "payload": payload, "agent_id": agent, "caller_signature": "sig"}

    clients = types.ModuleType("field_core.clients")
    clients.CallerSigner, clients.signed_append_body = CallerSigner, signed_append_body
    package = types.ModuleType("field_core")
    package.clients = clients
    monkeypatch.setitem(sys.modules, "field_core", package)
    monkeypatch.setitem(sys.modules, "field_core.clients", clients)
    monkeypatch.setattr(renew_token.Renewal, "add_repo_field_core", staticmethod(lambda: None))
    monkeypatch.setenv(renew_token.CALLER_ID_ENV, IDENT)
    monkeypatch.setenv(renew_token.CALLER_KEY_ENV, KEY)
    return state


def test_the_signer_and_its_key_are_loaded_once_across_two_appends(fake_field_core, capsys):
    run = bare()
    run.ledger("token.renewed", {"n": 1})
    run.ledger("token.renewed", {"n": 2})
    assert fake_field_core.loads == 1, "the key was read again for the second append"
    assert len(run.api.calls) == 2 and all(body["caller_signature"] == "sig" for _, _, body in run.api.calls)


def test_no_signer_is_remembered_too_the_environment_is_read_once(fake_field_core, monkeypatch):
    monkeypatch.delenv(renew_token.CALLER_ID_ENV)
    monkeypatch.delenv(renew_token.CALLER_KEY_ENV)
    run = bare()
    assert run.caller_signer() is None
    monkeypatch.setenv(renew_token.CALLER_ID_ENV, IDENT)
    monkeypatch.setenv(renew_token.CALLER_KEY_ENV, KEY)
    assert run.caller_signer() is None, "a later environment change reloaded a signer the run had settled"
    assert fake_field_core.loads == 0


def test_two_failed_appends_print_a_count_of_two(fake_field_core, monkeypatch, capsys):
    monkeypatch.delenv(renew_token.CALLER_ID_ENV)
    monkeypatch.delenv(renew_token.CALLER_KEY_ENV)
    run = bare(status=500)
    run.ledger("token.renewed", {"n": 1})
    run.ledger("token.renewed", {"n": 2})
    out = capsys.readouterr().out
    assert "dropped_ledger_appends=1" in out and "dropped_ledger_appends=2" in out
    assert out.index("dropped_ledger_appends=1") < out.index("dropped_ledger_appends=2")
    assert run.ledger_dropped == 2


def test_two_signing_failures_count_two_and_name_only_the_class(fake_field_core, capsys):
    fake_field_core.sign_raises = ValueError(CANARY)
    run = bare()
    run.ledger("token.renewed", {"n": 1})
    run.ledger("token.renewed", {"n": 2})
    out = capsys.readouterr().out
    assert "dropped_ledger_appends=2" in out and "ValueError" in out
    assert CANARY not in out and not any(piece in out for piece in SLICES)
    assert run.api.calls == [], "a body that could not be signed was sent"


def test_the_unavailable_line_names_the_exception_class_never_its_text(fake_field_core, capsys):
    fake_field_core.raises = RuntimeError(CANARY)
    run = bare()
    assert run.caller_signer() is None
    out = capsys.readouterr().out
    assert "caller signing unavailable (RuntimeError); appending unsigned" in out
    assert CANARY not in out and not any(piece in out for piece in SLICES)


def test_an_unusable_key_file_is_said_and_the_append_goes_out_unsigned(fake_field_core, capsys):
    fake_field_core.returns = None
    run = bare()
    run.ledger("token.renewed", {"n": 1})
    out = capsys.readouterr().out
    assert "caller signing unavailable (the key file is unusable); appending unsigned" in out
    assert "caller_signature" not in run.api.calls[0][2]


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_key_value_counts_as_not_set_and_names_the_variable(fake_field_core, monkeypatch, capsys, blank):
    monkeypatch.setenv(renew_token.CALLER_KEY_ENV, blank)
    run = bare()
    assert run.caller_signer() is None
    out = capsys.readouterr().out
    assert f"{renew_token.CALLER_KEY_ENV} is not set" in out and "appending unsigned" in out
    assert fake_field_core.loads == 0, "a blank key value was handed to the signer"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_identity_counts_as_not_set_and_names_the_variable(fake_field_core, monkeypatch, capsys, blank):
    monkeypatch.setenv(renew_token.CALLER_ID_ENV, blank)
    run = bare()
    assert run.caller_signer() is None
    out = capsys.readouterr().out
    assert f"{renew_token.CALLER_ID_ENV} is not set" in out
    assert KEY not in out and fake_field_core.loads == 0
