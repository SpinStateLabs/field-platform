"""Config helpers, decode_reason and halt_open_paths (scout S2-7, test gap).

Covers the small pure readers the other suites only use indirectly: they never
raise on a bad secret file, they strip and default consistently, and the
x-field-kill-reason header is decoded before it is cut to REASON_MAX.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from approver_fakes import default_map, set_map

from claude_approver import api, config
from claude_approver.core import REASON_MAX, decode_reason


# --- read_secret_file -------------------------------------------------------


def test_read_secret_file_returns_the_trimmed_content(tmp_path):
    p = tmp_path / "k"
    p.write_text("  sk-test-value\n", encoding="utf-8")
    assert config.read_secret_file(p) == "sk-test-value"


def test_read_secret_file_accepts_a_str_path(tmp_path):
    p = tmp_path / "k"
    p.write_text("abc\r\n", encoding="utf-8")
    assert config.read_secret_file(str(p)) == "abc"


def test_read_secret_file_missing_is_none(tmp_path):
    assert config.read_secret_file(tmp_path / "nope") is None


def test_read_secret_file_directory_is_none(tmp_path):
    assert config.read_secret_file(tmp_path) is None


def test_read_secret_file_invalid_utf8_is_none(tmp_path):
    p = tmp_path / "k"
    p.write_bytes(b"\xff\xfe\x00bad")
    assert config.read_secret_file(p) is None


@pytest.mark.parametrize("content", ["", " ", "\n", " \t\r\n  "])
def test_read_secret_file_blank_is_none(tmp_path, content):
    p = tmp_path / "k"
    p.write_text(content, encoding="utf-8")
    assert config.read_secret_file(p) is None


def test_read_secret_file_embedded_nul_in_path_does_not_raise():
    assert config.read_secret_file("bad\x00path") is None


# --- key_file_present / key_file_path ---------------------------------------


def test_key_file_present_follows_the_file(tmp_path, monkeypatch):
    p = tmp_path / "key"
    monkeypatch.setenv(config.ENV_KEY_FILE, str(p))
    assert config.key_file_present() is False  # missing
    p.write_text("  \n", encoding="utf-8")
    assert config.key_file_present() is False  # blank
    p.write_text("sk-x\n", encoding="utf-8")
    assert config.key_file_present() is True


def test_key_file_path_blank_env_uses_the_default(monkeypatch):
    monkeypatch.setenv(config.ENV_KEY_FILE, "   ")
    assert config.key_file_path() == Path(config.DEFAULT_KEY_FILE)


# --- environment_filter -----------------------------------------------------


def test_environment_filter_unset_is_none():
    assert config.environment_filter() is None


@pytest.mark.parametrize("raw", ["", "   "])
def test_environment_filter_blank_is_none(monkeypatch, raw):
    monkeypatch.setenv(config.ENV_ENVIRONMENT, raw)
    assert config.environment_filter() is None


def test_environment_filter_is_stripped(monkeypatch):
    monkeypatch.setenv(config.ENV_ENVIRONMENT, "  env_abc  ")
    assert config.environment_filter() == "env_abc"


# --- service_url ------------------------------------------------------------


def test_service_url_strips_trailing_slashes(monkeypatch):
    monkeypatch.setenv("SOME_URL", " http://x.test:1/// ")
    assert config.service_url("SOME_URL", "http://d") == "http://x.test:1"


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_service_url_blank_or_unset_uses_the_default(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("SOME_URL", raising=False)
    else:
        monkeypatch.setenv("SOME_URL", raw)
    assert config.service_url("SOME_URL", "http://default.test/") == "http://default.test"


# --- data_dir ---------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   "])
def test_data_dir_blank_uses_var(monkeypatch, raw):
    monkeypatch.setenv("FIELD_DATA_DIR", raw)
    assert config.data_dir() == Path("./var")


def test_data_dir_honours_the_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_DATA_DIR", f" {tmp_path} ")
    assert config.data_dir() == tmp_path


# --- decode_reason ----------------------------------------------------------


def test_decode_reason_none_stays_none():
    assert decode_reason(None) is None


def test_decode_reason_empty_string_is_empty():
    assert decode_reason("") == ""


def test_decode_reason_percent_decodes():
    assert decode_reason("halted%20by%20operator%3A%20%C3%A9") == "halted by operator: \u00e9"


def test_decode_reason_malformed_escape_is_left_as_is():
    assert decode_reason("100%zz done") == "100%zz done"


def test_decode_reason_truncates_after_decoding():
    # 600 encoded chars decode to 200; a cut applied BEFORE decoding would keep fewer.
    raw = "%41" * 200
    assert decode_reason(raw) == "A" * 200
    # 3 encoded chars per decoded char: still 512 decoded chars, not 512 raw chars.
    assert decode_reason("%41" * 600) == "A" * REASON_MAX


def test_decode_reason_plain_text_is_cut_to_the_limit():
    out = decode_reason("x" * (REASON_MAX + 50))
    assert out == "x" * REASON_MAX and len(out) == REASON_MAX


def test_decode_reason_multibyte_at_the_limit_does_not_raise():
    raw = "a" * (REASON_MAX - 1) + "%C3%A9" + "%C3%A9"
    out = decode_reason(raw)
    assert len(out) == REASON_MAX
    assert out.endswith("\u00e9")


def test_decode_reason_invalid_utf8_escape_does_not_raise():
    out = decode_reason("a%FFb")
    assert out is not None and out.startswith("a") and out.endswith("b")


# --- halt_open_paths --------------------------------------------------------


def test_halt_open_paths_is_empty_without_a_map():
    assert api.halt_open_paths() == set()


def test_halt_open_paths_one_path_per_usable_id(monkeypatch):
    mapping = default_map()
    mapping["console-2"] = {"field_agent_id": "agent-two"}
    mapping["console-bad"] = {"token_id": "t"}  # no field_agent_id: unusable
    set_map(monkeypatch, mapping)
    ids = {e["field_agent_id"] for e in mapping.values() if isinstance(e, dict) and e.get("field_agent_id")}
    assert api.halt_open_paths() == {f"/halt/{i}" for i in ids}
    assert len(api.halt_open_paths()) == 2


def test_halt_open_paths_two_consoles_one_field_id_is_one_path(monkeypatch):
    mapping = default_map()
    fid = next(v["field_agent_id"] for v in mapping.values() if isinstance(v, dict))
    mapping["console-2"] = {"field_agent_id": fid}
    set_map(monkeypatch, mapping)
    assert api.halt_open_paths() == {f"/halt/{fid}"}


def test_an_id_added_after_create_app_is_not_open_until_restart(monkeypatch):
    """The docstring's contract: open paths are computed once at app creation,
    so under an armed perimeter a later-added id's /halt answers 401."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("FIELD_SHARED_SECRET", "perimeter-test-secret")
    set_map(monkeypatch, default_map())
    fid = next(v["field_agent_id"] for v in default_map().values() if isinstance(v, dict))
    app = api.create_app()
    later = default_map()
    later["console-late"] = {"field_agent_id": "late-agent"}
    set_map(monkeypatch, later)
    client = TestClient(app)
    assert client.post("/halt/late-agent").status_code == 401  # not open yet
    assert client.post(f"/halt/{fid}").status_code != 401  # open since creation
    # a restart (a fresh create_app) picks the new id up
    assert TestClient(api.create_app()).post("/halt/late-agent").status_code != 401
