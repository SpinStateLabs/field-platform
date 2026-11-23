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

#: The estate this tool must read, written out here and NOT taken from the tool's own table: the proxy paths are the
#: ones integration/demo/Caddyfile routes (/registry /ledger /delegation /killswitch /governor /federation /lifecycle,
#: and the console owns the root), so a wrong path or a dropped service in the tool shows up as a 404 or a missing check.
LITERAL = (
    ("/registry/health", "agent-registry"),
    ("/ledger/health", "sealed-ledger"),
    ("/delegation/health", "delegation-authority"),
    ("/killswitch/health", "kill-switch"),
    ("/governor/health", "spend-governor"),
    ("/federation/health", "federation-broker"),
    ("/lifecycle/health", "lifecycle-manager"),
    ("/health", "ops-console"),
)


def healthy(service, sha=SHA, **over):
    return {"service": service, "build_sha": sha, **BLANK, **over}


class FakeEstate:
    def __init__(self, overrides=None, drop=(), status=None):
        self.overrides, self.drop, self.status = overrides or {}, set(drop), status or {}
        self.requests: list[tuple[str, str, bool]] = []
        est = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _serve(self):
                est.requests.append((self.command, self.path, "x-field-auth" in self.headers))
                for path, service in LITERAL:
                    if self.path == path and path not in est.drop:
                        body = est.overrides.get(path, healthy(service))
                        data = json.dumps(body).encode()
                        self.send_response(est.status.get(path, 200))
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


# ---- review conditions (reviewer-7 on 989f14b): the table is pinned literally, boundaries are pinned ---------------

def test_the_tool_checks_exactly_the_eight_services_at_their_literal_proxy_paths():
    assert tuple((path, service) for _l, path, service in sc.OPERATOR_BLOCK_SERVICES) == LITERAL
    assert len({label for label, _p, _s in sc.OPERATOR_BLOCK_SERVICES}) == 8


def test_a_run_requests_each_of_the_eight_literal_paths_once(estate, capsys):
    e = estate()
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 0, out
    assert sorted(p for _m, p, _a in e.requests) == sorted(p for p, _s in LITERAL)


@pytest.mark.parametrize("path", [p for p, _s in LITERAL])
def test_a_stopped_service_fails_the_whole_check_whichever_it_is(estate, capsys, path):
    code, out = run(estate(drop=[path]), capsys, "--expect-build-sha", SHA)
    assert code == 1 and f"[FAIL] {path} answers 200" in out


@pytest.mark.parametrize("path,service", LITERAL)
def test_each_service_must_answer_as_itself(estate, capsys, path, service):
    other = "not-" + service
    code, out = run(estate(overrides={path: healthy(other)}), capsys, "--expect-build-sha", SHA)
    assert code == 1 and f"[FAIL] {path} answers 200 as {service}" in out


def test_a_non_200_answer_fails_even_with_a_healthy_looking_body(estate, capsys):
    e = estate(status={"/ledger/health": 503})
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 1 and "[FAIL] /ledger/health answers 200 as sealed-ledger (HTTP 503)" in out


def test_identity_present_missing_fails_closed(estate, capsys):
    body = {k: v for k, v in healthy("agent-registry").items() if k != "identity_present"}
    code, out = run(estate(overrides={"/registry/health": body}), capsys, "--expect-build-sha", SHA)
    assert code == 1 and "[FAIL] registry: every operator flag blank (identity_present is not false)" in out


def test_an_empty_string_identity_id_counts_as_blank(estate, capsys):
    over = {"/registry/health": healthy("agent-registry", operator_identity_id="")}
    code, out = run(estate(overrides=over), capsys, "--expect-build-sha", SHA)
    assert code == 0, out


def test_a_full_build_id_is_never_printed_even_when_a_check_fails(estate, capsys):
    e = estate(overrides={"/ledger/health": healthy("sealed-ledger", sha=OTHER)})
    code, out = run(e, capsys, "--expect-build-sha", SHA)
    assert code == 1 and SHA not in out and OTHER not in out
    code, out = run(e, capsys)
    assert code == 1 and SHA not in out and OTHER not in out


def test_the_template_and_the_tool_say_behaves_off_not_unset():
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "templates" / "stage0-deploy-record.md").read_text(encoding="utf-8")
    assert "unset in every" not in text and "operator_mode` off" in text and "cannot prove a variable is unset" in text
    assert "is blank, seen from" not in Path(sc.__file__).read_text(encoding="utf-8")
