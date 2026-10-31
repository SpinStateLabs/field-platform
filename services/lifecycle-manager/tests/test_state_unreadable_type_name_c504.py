"""C-504: GET /findings on state it cannot read says what failed by class name.

An OSError's text carries the path it tried (a server directory); a JSON error's
text carries nothing sensitive but is still not this route's to relay. The 500
reply and the log hold the name only."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from lifecycle_manager.api import create_app

# Built from parts so the marker is not a literal in the tree.
CANARY = "tkv-" + "c504" + "-canary" + "-" + "dir-7d21b4"
SLICES = sorted({CANARY[i:i + 8] for i in range(0, len(CANARY) - 7, 4)} | {CANARY})


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / CANARY))
    return TestClient(create_app())


def _clean(text: str) -> None:
    for marker in SLICES:
        assert marker not in text, f"state path reached the output: slice of length {len(marker)}"


def test_an_unreadable_findings_file_is_named_by_its_error_class_only(tmp_path, monkeypatch, caplog):
    client = _app(tmp_path, monkeypatch)
    state = tmp_path / CANARY / "lifecycle" / "last_sweep.json"
    state.mkdir(parents=True)  # a directory where the file should be: read_text raises with the path
    with caplog.at_level(logging.DEBUG):
        r = client.get("/findings")
    assert r.status_code == 500
    assert r.json()["detail"] == "lifecycle state unreadable: IsADirectoryError"
    _clean(r.text + " ".join(rec.getMessage() for rec in caplog.records))


def test_a_corrupt_findings_file_is_named_by_its_error_class_only(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    state = tmp_path / CANARY / "lifecycle" / "last_sweep.json"
    state.parent.mkdir(parents=True)
    state.write_text("{not json " + CANARY, encoding="utf-8")
    r = client.get("/findings")
    assert r.status_code == 500
    assert r.json()["detail"] == "lifecycle state unreadable: JSONDecodeError"
    _clean(r.text)
