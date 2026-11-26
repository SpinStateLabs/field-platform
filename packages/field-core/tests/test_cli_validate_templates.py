"""S3-5: `field validate` and `field templates` end in a one-line exit 2 on an
unreadable or unparseable manifest and on an unknown template, never a traceback
(validation.py promises 'a gap report, not a stack trace')."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from field_core import cli
from field_core.templates_api import TEMPLATE_NAMES

runner = CliRunner()


def _bad_files(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    y = tmp_path / "bad.yaml"
    y.write_text("{", encoding="utf-8")
    lst = tmp_path / "list.yaml"
    lst.write_text("- a\n- b\n", encoding="utf-8")
    u = tmp_path / "utf.yaml"
    u.write_bytes(b"\xff\xfe\x00bad")
    return {"directory": d, "bad-yaml": y, "yaml-list": lst, "invalid-utf8": u}


@pytest.mark.parametrize("kind", ["directory", "bad-yaml", "yaml-list", "invalid-utf8"])
@pytest.mark.parametrize("as_json", [False, True])
def test_an_unreadable_manifest_is_a_one_line_exit_2(tmp_path, kind, as_json):
    path = _bad_files(tmp_path)[kind]
    res = runner.invoke(cli.app, ["validate", str(path), *(["--json"] if as_json else [])])
    assert res.exit_code == 2
    assert isinstance(res.exception, SystemExit)
    assert "error: cannot read manifest" in res.output
    assert "Traceback" not in res.output
    assert len(res.output.strip().splitlines()) == 1


def test_a_missing_file_is_still_exit_2(tmp_path):
    res = runner.invoke(cli.app, ["validate", str(tmp_path / "nope.yaml")])
    assert res.exit_code == 2 and "no manifest at" in res.output


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_a_shipped_template_round_trips_through_validate(tmp_path, name):
    p = tmp_path / "m.yaml"
    assert runner.invoke(cli.app, ["templates", "--show", name, "--out", str(p)]).exit_code == 0
    res = runner.invoke(cli.app, ["validate", str(p), "--json"])
    assert res.exit_code in (0, 1), res.output
    assert json.loads(res.output)["status"]


def test_an_invalid_manifest_is_exit_1(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("unrelated: 1\n", encoding="utf-8")
    assert runner.invoke(cli.app, ["validate", str(p)]).exit_code == 1


def test_templates_lists_the_four_names():
    res = runner.invoke(cli.app, ["templates"])
    assert res.exit_code == 0
    assert res.output.split() == list(TEMPLATE_NAMES)


def test_an_unknown_template_names_the_known_ones_and_exits_2():
    res = runner.invoke(cli.app, ["templates", "--show", "nope"])
    assert res.exit_code == 2
    assert isinstance(res.exception, SystemExit)
    for n in TEMPLATE_NAMES:
        assert n in res.output
    assert "Traceback" not in res.output


def test_an_unwritable_out_is_a_one_line_exit_2(tmp_path):
    res = runner.invoke(cli.app, ["templates", "--show", "default", "--out", str(tmp_path)])
    assert res.exit_code == 2
    assert isinstance(res.exception, SystemExit)
    assert "error: cannot write" in res.output
