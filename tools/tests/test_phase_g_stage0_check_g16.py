"""G16: phase_g_stage0_check reads /health of the eight operator-block services and reports the build id and that
every operator flag is blank. A fake estate (stdlib HTTP server) serves made-up /health bodies; the tool sends GETs only
and prints no secret. Every id, hash and value here is made up."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import phase_g_stage0_check as sc  # noqa: E402

SHA = "ab12cd34" * 5                      # 40 hex
OTHER = "ef56ab78" * 5
SECRET_LOOKING = "fok_" + "Z9y8X7w6" * 4   # must never be printed
BLANK = {"operator_mode": "off", "identity_present": False, "operator_identity_id": None}


def healthy(service, sha=SHA, **over):
    return {"service": service, "build_sha": sha, **BLANK, **over}


class FakeEstate:
    def __init__(self, overrides=None, drop=()):
        self.overrides, self.drop = overrides or {}, set(drop)
        self.requests: list[tuple[str, str, bool]] = []
        est = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _serve(self):
                est.requests.append((self.command, self.path, "x-field-auth" in self.headers))
                for _label, path, service in sc.OPERATOR_BLOCK_SERVICES:
                    if self.path == path and path not in est.drop:
                        body = est.overrides.get(path, healthy(service))
                        data = json.dumps(body).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def estate():
    made = []

    def make(**kw):
        e = FakeEstate(**kw)
        made.append(e)
        return e
    yield make
    for e in made:
        e.close()


def run(e, capsys, *extra):
    code = sc.main(["--base", e.base, *extra])
    return code, capsys.readouterr().out


def test_blank_flags_and_one_build_id_pass_and_only_get_health_is_sent(estate, capsys):
    e = estate()
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 0, out
    assert "[FAIL]" not in out and SHA[:12] in out and SHA not in out
    assert {m for m, _, _ in e.requests} == {"GET"} and all(p.endswith("/health") for _, p, _ in e.requests)
    assert not any(auth for _, _, auth in e.requests)        # no credential is ever sent


def test_without_an_expected_sha_all_eight_must_agree(estate, capsys):
    e = estate(overrides={"/ledger/health": healthy("sealed-ledger", sha=OTHER)})
    code, out = run(e, capsys)
    assert code == 1 and "run one build id" in out.split("[FAIL]")[-1]


def test_a_service_on_another_build_fails_the_expected_sha(estate, capsys):
    e = estate(overrides={"/killswitch/health": healthy("kill-switch", sha=OTHER)})
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 1 and "killswitch: build id" in out


@pytest.mark.parametrize("over", [
    {"operator_mode": "log-only"}, {"operator_mode": "enforce"}, {"identity_present": True},
    {"operator_identity_id": "svc-x"}, {"operator_mode": None},
], ids=["log-only", "enforce", "identity-present", "identity-id", "mode-null"])
def test_any_set_operator_flag_fails(estate, capsys, over):
    e = estate(overrides={"/registry/health": healthy("agent-registry", **over)})
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 1 and "[FAIL] registry: every operator flag blank" in out


def test_a_service_without_the_operator_block_fails_closed(estate, capsys):
    body = {"service": "spend-governor", "build_sha": SHA}
    code, out = run(estate(overrides={"/governor/health": body}), capsys, "--expect-build-sha", SHA)
    assert code == 1 and "operator block is absent" in out


def test_a_missing_service_and_a_wrong_service_name_fail(estate, capsys):
    assert run(estate(drop=["/delegation/health"]), capsys, "--expect-build-sha", SHA)[0] == 1
    e = estate(overrides={"/ledger/health": healthy("not-the-ledger")})
    assert run(e, capsys, "--expect-build-sha", SHA)[0] == 1


def test_nothing_secret_is_printed_whatever_the_health_body_holds(estate, capsys):
    over = {"/registry/health": healthy("agent-registry", operator_identity_id=SECRET_LOOKING, note=SECRET_LOOKING,
                                        operator_roster_sha16="0123456789abcdef")}
    code, out = run(estate(overrides=over), capsys, "--expect-build-sha", SHA)
    assert code == 1
    assert SECRET_LOOKING not in out and "0123456789abcdef" not in out


@pytest.mark.parametrize("bad", ["abc", "g" * 40, SHA[:-1]])
def test_a_malformed_expected_sha_is_a_usage_error(bad, capsys):
    assert sc.main(["--base", "http://127.0.0.1:9", "--expect-build-sha", bad]) == 2


def test_an_unreachable_estate_fails_not_passes(capsys):
    assert sc.main(["--base", "http://127.0.0.1:9"]) == 1


def test_the_template_names_no_estate_fact():
    import re
    text = (Path(__file__).resolve().parents[2] / "docs" / "templates" / "stage0-deploy-record.md").read_text(encoding="utf-8")
    assert not re.search(r"\d+\.\d+\.\d+\.\d+|https?://|fok_|[0-9a-f]{12,}", text)
    assert "phase_g_stage0_check.py" in text
