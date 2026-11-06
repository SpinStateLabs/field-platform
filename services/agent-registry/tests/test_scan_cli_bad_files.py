"""S5-3: `registry scan` with a missing, unreadable, non-UTF-8, malformed or oversized input file is exit 2 with one named
`error:` line (stdout empty, no traceback, no file bytes quoted). The n8n file gets the same 1 MiB cap as the other inputs."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.redaction import MAX_SCAN_BYTES

OPTIONS = ["--n8n", "--accounts", "--api-keys", "--secrets-text", "--principals"]
MARK = "SYNTHETIC-MARKER-0123"


def run(tmp_path, *args):
    db = tmp_path / "reg.sqlite3"
    runner = CliRunner(mix_stderr=False) if "mix_stderr" in CliRunner.__init__.__code__.co_varnames else CliRunner()
    return runner.invoke(cli.app, ["scan", *args, "--path", str(db)])


def assert_named_refusal(r, *forbidden):
    assert r.exit_code == 2, (r.exit_code, r.output)
    err = r.stderr if r.stderr_bytes is not None else r.output
    assert "Traceback" not in err and "Traceback" not in r.output
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error:"), err
    assert r.stdout.strip() == ""
    for f in forbidden:
        assert f not in err


@pytest.mark.parametrize("opt", OPTIONS)
def test_a_missing_file_is_a_named_exit_2(tmp_path, opt):
    # --principals alone scans nothing: pair it with a real --api-keys file
    extra = []
    if opt == "--principals":
        keys = tmp_path / "k.csv"
        keys.write_text("key_name,owner,service,created,last_used\n", encoding="utf-8")
        extra = ["--api-keys", str(keys)]
    r = run(tmp_path, opt, str(tmp_path / "does-not-exist.txt"), *extra)
    assert_named_refusal(r)
    assert "does-not-exist.txt" in r.stderr and "cannot be read" in r.stderr


@pytest.mark.parametrize("opt", OPTIONS[1:])
def test_a_directory_is_a_named_exit_2(tmp_path, opt):
    d = tmp_path / "adir"
    d.mkdir()
    extra = []
    if opt == "--principals":
        keys = tmp_path / "k.csv"
        keys.write_text("key_name,owner,service,created,last_used\n", encoding="utf-8")
        extra = ["--api-keys", str(keys)]
    assert_named_refusal(run(tmp_path, opt, str(d), *extra))


def test_a_binary_n8n_file_is_exit_2_and_quotes_no_bytes(tmp_path):
    f = tmp_path / "wf.json"
    f.write_bytes(MARK.encode() + b"\xff\xfe")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r, MARK)
    assert "not UTF-8 text" in r.stderr


@pytest.mark.parametrize("body", ["{not json", "", "[1, 2", MARK + " {"])
def test_invalid_json_n8n_is_exit_2_and_quotes_no_content(tmp_path, body):
    f = tmp_path / "wf.json"
    f.write_text(body, encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r, MARK, "{not json")
    assert "not valid JSON" in r.stderr


def test_a_deeply_nested_n8n_file_is_exit_2_not_a_recursion_error(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    assert_named_refusal(run(tmp_path, "--n8n", str(f)))


def test_an_oversized_n8n_file_is_exit_2(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[" + " " * (2 * 1024 * 1024) + "]", encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r)
    assert "1 MiB" in r.stderr


def test_an_oversized_text_input_is_exit_2(tmp_path):
    f = tmp_path / "keys.csv"
    f.write_text("x" * (MAX_SCAN_BYTES + 1), encoding="utf-8")
    assert_named_refusal(run(tmp_path, "--secrets-text", str(f)))


def test_an_n8n_file_of_exactly_1_mib_is_scanned(tmp_path):
    f = tmp_path / "wf.json"
    body = "[" + " " * (MAX_SCAN_BYTES - 2) + "]"
    assert len(body.encode()) == MAX_SCAN_BYTES
    f.write_text(body, encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert r.exit_code == 0, r.output


def test_a_good_n8n_file_still_works(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[]", encoding="utf-8")
    assert run(tmp_path, "--n8n", str(f)).exit_code == 0


# --- review conditions (Lane O): the reader pinned directly, whole messages, other inputs, bytes read -------------------

from agent_registry import discover as _discover  # noqa: E402
from agent_registry.redaction import ScanInputError  # noqa: E402


def _err(path):
    with pytest.raises(ScanInputError) as e:
        _discover.read_scan_file(path)
    return str(e.value)


def test_a_nul_byte_in_the_path_is_a_named_refusal_not_a_value_error(tmp_path):
    assert _err(str(tmp_path / "a\x00b.txt")) == "a\x00b.txt cannot be read"


def test_the_whole_message_is_the_base_name_and_a_fixed_phrase_never_the_directory(tmp_path):
    missing = tmp_path / "deeply" / "nested" / "gone.txt"
    msg = _err(missing)
    assert msg == "gone.txt cannot be read" and str(tmp_path) not in msg
    d = tmp_path / "adir"
    d.mkdir()
    assert _err(d) == "adir cannot be read"


def test_a_non_utf8_message_has_no_decoder_text_byte_value_or_position(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"ok" + b"\xff\xfe" + MARK.encode())
    assert _err(f) == "x.bin is not UTF-8 text"


def test_the_oversize_message_states_the_exact_cap(tmp_path):
    f = tmp_path / "big.txt"
    f.write_bytes(b"x" * (MAX_SCAN_BYTES + 1))
    assert _err(f) == f"big.txt is larger than the scanner accepts: at most {MAX_SCAN_BYTES} bytes (1 MiB)"


def test_invalid_n8n_json_names_the_file_and_nothing_else(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScanInputError) as e:
        _discover.load_n8n_file(str(f))
    assert str(e.value) == "wf.json is not valid JSON"


def test_exactly_the_cap_is_read_whole_for_any_input_and_one_over_is_refused(tmp_path):
    f = tmp_path / "keys.csv"
    f.write_bytes(b"a" * MAX_SCAN_BYTES)
    assert len(_discover.read_scan_file(f)) == MAX_SCAN_BYTES                      # no silent truncation
    f.write_bytes(b"a" * (MAX_SCAN_BYTES + 1))
    assert "larger than the scanner accepts" in _err(f)


class _CountingFile:
    def __init__(self, data):
        self.data, self.sizes = data, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, size=-1):
        self.sizes.append(size)
        return self.data if size is None or size < 0 else self.data[:size]


def test_an_oversized_file_is_never_read_past_the_cap_plus_one_byte(monkeypatch):
    fake = _CountingFile(b"x" * (MAX_SCAN_BYTES * 3))
    monkeypatch.setattr(_discover, "open", lambda *a, **k: fake, raising=False)
    assert "larger than the scanner accepts" in _err("big.txt")
    assert fake.sizes == [MAX_SCAN_BYTES + 1]                                       # one bounded read, never unbounded


@pytest.mark.parametrize("opt", ["--accounts", "--api-keys", "--secrets-text"])
def test_a_missing_or_binary_csv_style_input_is_named_not_a_traceback(tmp_path, opt):
    r = run(tmp_path, opt, str(tmp_path / "nope.csv"))
    assert_named_refusal(r)
    assert "nope.csv" in r.stderr and "cannot be read" in r.stderr
    b = tmp_path / "bin.csv"
    b.write_bytes(MARK.encode() + b"\xff\xfe")
    r = run(tmp_path, opt, str(b))
    assert_named_refusal(r, MARK)
    assert "bin.csv is not UTF-8 text" in r.stderr
