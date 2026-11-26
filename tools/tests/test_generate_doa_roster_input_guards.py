"""S4-19: duplicate registry agent_ids are refused (naming the second record's index) and an unwritable --out is a
REFUSED line (exit 2, exception class only), never a traceback."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from test_generate_doa_roster import gen, manifest, record


@pytest.fixture()
def estate(tmp_path):
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    manifest(mdir, "inv", "Don Co", "Don Co", ["a"])
    manifest(mdir, "time", "Don Co", "Jane Doe", ["b"])
    return tmp_path


def go(tmp_path: Path, records: list[dict], out: Path):
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(records), encoding="utf-8")
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        code = gen.main(["--registry", str(registry), "--manifests", str(tmp_path / "manifests"), "--out", str(out)])
    return code, so.getvalue(), se.getvalue()


# ---- duplicate agent ids --------------------------------------------------------------------------------------------

def test_a_duplicate_agent_id_is_refused_naming_the_second_record(estate):
    out = estate / "o" / "r.yaml"
    code, _, err = go(estate, [record("inv"), record("time"), record("inv", status="retired")], out)
    assert code == 2 and "REFUSED" in err and "Traceback" not in err
    assert "record 2" in err and "duplicate" in err
    assert not out.exists()


def test_two_manifest_refs_for_one_agent_are_refused(estate):
    out = estate / "o" / "r.yaml"
    dup = record("inv")
    dup["manifest_ref"] = "/data/manifests/time.yaml"
    code, _, err = go(estate, [record("inv"), dup], out)
    assert code == 2 and "record 1" in err and not out.exists()


def test_distinct_agent_ids_still_work(estate):
    out = estate / "o" / "r.yaml"
    code, stdout, err = go(estate, [record("inv"), record("time")], out)
    assert code == 0, err
    assert out.exists()


def test_ids_differing_only_by_case_are_distinct(estate):
    # agent ids are compared exactly everywhere else in this tool: no new equivalence is introduced
    out = estate / "o" / "r.yaml"
    manifest(estate / "manifests", "Inv", "Don Co", "Don Co", ["a"])
    code, _, err = go(estate, [record("inv"), record("Inv")], out)
    assert code == 0, err


# ---- unwritable --out -----------------------------------------------------------------------------------------------

def test_out_naming_a_directory_is_refused(estate):
    out = estate / "adir"
    out.mkdir()
    code, _, err = go(estate, [record("inv")], out)
    assert code == 2 and "REFUSED" in err and "Traceback" not in err
    assert "IsADirectoryError" in err or "OSError" in err or "Error" in err
    assert out.is_dir() and not list(out.iterdir())


def test_out_under_a_file_is_refused_and_no_tmp_left(estate):
    blocker = estate / "afile"
    blocker.write_text("x", encoding="utf-8")
    code, _, err = go(estate, [record("inv")], blocker / "sub" / "r.yaml")
    assert code == 2 and "REFUSED" in err and "Traceback" not in err
    assert blocker.read_text(encoding="utf-8") == "x"


def test_refusal_names_the_exception_class_only(estate, monkeypatch):
    out = estate / "o" / "r.yaml"
    secret = "SYNTHETIC-PATH-MARK"

    real = Path.write_text

    def boom(self, *a, **k):
        if self.name.endswith(".tmp"):
            raise PermissionError(13, secret)
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", boom)
    code, _, err = go(estate, [record("inv")], out)
    assert code == 2 and "PermissionError" in err and secret not in err
    assert not out.exists()
