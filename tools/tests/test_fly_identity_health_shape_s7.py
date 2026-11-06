"""S7-33 — fly_identity_check: a /health body that is not a JSON object is a named problem and the run
still ends with its C5-RESULT line (the CI fly-image-smoke job and the Stage 4 scripts grep for it);
service_of is pinned directly. The script stays standard-library only."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fly_identity_check as fic  # noqa: E402

NOT_OBJECTS = [[], [1], ["registry"], "ok", "_error", 5, 1.5, True, None]


@pytest.mark.parametrize("bad", NOT_OBJECTS, ids=lambda v: repr(v))
def test_check_health_names_a_non_object_value_instead_of_raising(bad):
    assert fic.check_health({"registry": bad}, "none") == ["registry: /health unreadable (NotAnObject)"]


def test_check_health_mixes_good_and_bad_services():
    problems = fic.check_health(
        {"registry": [], "ledger": {"operator_identity_id": None, "identity_present": False},
         "console": {"_error": "URLError"}}, "none")
    assert problems == ["registry: /health unreadable (NotAnObject)",
                        "console: /health unreadable (URLError)"]


def test_check_health_unchanged_for_good_bodies():
    good = {"registry": {"operator_identity_id": "svc-registry", "identity_present": True}}
    assert fic.check_health(good, "four") == []
    assert len(fic.check_health(good, "none")) == 1


class _Handler(BaseHTTPRequestHandler):
    body = b"[]"

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.parametrize("raw", [b"[]", b'"text"', b"5", b"null", b"true"])
def test_health_stores_not_an_object_for_a_non_object_answer(server, raw):
    srv, base = server
    _Handler.body = raw
    got = fic._health(base, timeout=2)
    assert set(got) == set(fic.HEALTH_PREFIX)
    assert all(v == {"_error": "NotAnObject"} for v in got.values())


def test_health_keeps_an_object_answer(server):
    srv, base = server
    _Handler.body = json.dumps({"operator_identity_id": "x", "identity_present": True}).encode()
    assert all(v["operator_identity_id"] == "x" for v in fic._health(base, timeout=2).values())


def test_main_still_ends_with_a_c5_result_line_on_a_non_object_health(server, tmp_path, capsys):
    srv, base = server
    _Handler.body = b"[]"
    proc = tmp_path / "proc"
    proc.mkdir()
    import os
    old = os.environ.get("PROC_ROOT")
    os.environ["PROC_ROOT"] = str(proc)
    try:
        rc = fic.main(["--expect", "none", "--key-dir", str(tmp_path / "keys"), "--health", base])
    finally:
        if old is None:
            os.environ.pop("PROC_ROOT", None)
        else:
            os.environ["PROC_ROOT"] = old
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 1
    assert out[-1].startswith("C5-RESULT: FAIL")
    assert any("/health unreadable (NotAnObject)" in ln for ln in out)


# --- service_of --------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv, want", [
    ([b"/opt/field/bin/console", b"serve"], "console"),
    ([b"python", b"/x/killswitch", b"serve", b"--port", b"1"], "killswitch"),
    ([b"python3", b"-u", b"/a/b/registry", b"serve"], "registry"),
    ([b"serve"], None),                                   # a bare serve names no service
    ([b"serve", b"console"], None),                       # the name is the LAST element, after the verb
    ([b"python", b"/x/console"], None),                   # the name is last with no verb
    ([b"/x/console", b"status"], None),                   # a service path with a different verb
    ([b"/x/notaservice", b"serve"], None),
    ([b"/x/registry-ui", b"serve"], None),
    ([], None),
    ([b"/x/\xff\xfe/ledger", b"serve"], "ledger"),        # non-UTF-8 elsewhere in the path
    ([b"/x/led\xffger", b"serve"], None),                 # non-UTF-8 inside the service name
])
def test_service_of(argv, want):
    assert fic.service_of(argv) == want
