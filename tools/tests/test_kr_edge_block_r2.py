"""Key rotation slice R2 (design v0.2 section 8 row 2, S12): the two internal routes
``POST /operator/verify-hash`` and ``GET /operator/rotation-state`` exist on each of
the eight operator-block services, and the edge refuses them except from loopback:

* integration/demo/Caddyfile (the route map compose-smoke uses and the GB10's
  Caddyfile.gb10 imports for BOTH listeners) and integration/fly/Caddyfile (the
  Fly edge's only way in) refuse them with 403 before any handle / handle_path,
  unless the request comes from the proxy's own loopback with no proxy hop in
  front (the GB10 TLS site hands every request to 127.0.0.1:8080 and its
  reverse_proxy sets X-Forwarded-For, so 18443 is refused too);
* the CI jobs prove it on the real containers (compose-smoke, compose-upgrade-smoke
  on 18080 and 18443, fly-image-smoke): integration/demo/fixtures/kr-edge/check_edge_block.py
  from the runner, and a request from inside the proxy that must reach the service.

Static: reads the Caddyfiles and ci.yml (no docker, no network); builds each
service's app in process. Each mutant at the bottom must turn a check RED.
Test key values are throwaway constants."""

from __future__ import annotations

import fnmatch
import importlib
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CADDY_BASE = REPO / "integration" / "demo" / "Caddyfile"
CADDY_GB10 = REPO / "integration" / "demo" / "Caddyfile.gb10"
CADDY_FLY = REPO / "integration" / "fly" / "Caddyfile"
CI = REPO / ".github" / "workflows" / "ci.yml"
CHECKER = REPO / "integration" / "demo" / "fixtures" / "kr-edge" / "check_edge_block.py"

ROUTES = ("/operator/verify-hash", "/operator/rotation-state")
#: every Caddy prefix of an operator-block service, and "" for the console catch-all
PREFIXES = ("/registry", "/ledger", "/delegation", "/killswitch", "/governor", "/federation",
            "/lifecycle", "")
MARKER = "/__field_internal_route_refused"
EDGE_BODY = "internal route: loopback only"
LOOPBACK = "not remote_ip 127.0.0.0/8 ::1"
XFF = "header X-Forwarded-For *"

#: service -> its app module (the eight operator-block services)
APPS = {
    "sealed-ledger": "sealed_ledger.api", "agent-registry": "agent_registry.api",
    "delegation-authority": "delegation_authority.api", "kill-switch": "kill_switch.api",
    "spend-governor": "spend_governor.api", "federation-broker": "federation_broker.api",
    "ops-console": "ops_console.api", "lifecycle-manager": "lifecycle_manager.api",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def _code(caddy: str) -> list[str]:
    return [ln.split("#", 1)[0].strip() for ln in caddy.splitlines()
            if ln.split("#", 1)[0].strip()]


def _site(caddy: str, header: str) -> list[str]:
    """The directive lines of one top-level site block (nested lines included)."""
    lines, out, depth, inside = _code(caddy), [], 0, False
    for ln in lines:
        if not inside:
            if depth == 0 and ln == header + " {":
                inside, depth = True, 1
                continue
            depth += ln.count("{") - ln.count("}")
            continue
        depth += ln.count("{") - ln.count("}")
        if depth == 0:
            return out
        out.append(ln)
    raise AssertionError(f"no site {header!r}")


def _matcher(site: list[str], name: str) -> list[str]:
    assert f"@{name} {{" in site, f"no @{name} matcher"
    i = site.index(f"@{name} {{")
    j = site.index("}", i)
    return site[i + 1:j]


def _caddy_path_match(pattern: str, path: str) -> bool:
    """Caddy's path matcher: case-insensitive; `*` at both ends is a substring match,
    at one end a prefix / suffix match."""
    p, s = pattern.lower(), path.lower()
    if p.startswith("*") and p.endswith("*") and len(p) > 1:
        return p[1:-1] in s
    return fnmatch.fnmatchcase(s, p)


# --- checks (each raises AssertionError on a violation; the mutants reuse them) ----------------


def check_edge_site(caddy: str, header: str = ":8080") -> None:
    site = _site(caddy, header)
    # the matchers come first, before any handle (readability; Caddy orders rewrite first anyway)
    first_handle = next(i for i, ln in enumerate(site) if ln.startswith(("handle", "handle_path")))
    remote, fwd = _matcher(site, "kr_internal_remote"), _matcher(site, "kr_internal_forwarded")
    assert site.index("@kr_internal_remote {") < first_handle
    for m in (remote, fwd):
        paths = [ln for ln in m if ln.startswith("path ")]
        assert len(paths) == 1, m
        patterns = paths[0].split()[1:]
        for prefix in PREFIXES:
            for route in ROUTES:
                for variant in (prefix + route, prefix + route + "/", (prefix + route).upper(),
                                prefix + route + "/extra"):
                    assert any(_caddy_path_match(p, variant) for p in patterns), (m, variant)
        assert not any(_caddy_path_match(p, prefix + "/health") for p in patterns for prefix in PREFIXES)
    assert LOOPBACK in remote and len(remote) == 2, remote
    assert XFF in fwd and len(fwd) == 2, fwd
    # the refusal is a site-level rewrite (runs before every handle / handle_path) into one
    # handle that answers itself and proxies nothing
    assert f"rewrite @kr_internal_remote {MARKER}" in site
    assert f"rewrite @kr_internal_forwarded {MARKER}" in site
    i = site.index(f"handle {MARKER} {{")
    assert site[i + 1:i + 3] == [f'respond "{EDGE_BODY}" 403', "}"], site[i:i + 3]
    # nothing may strip X-Forwarded-For anywhere (that would let a proxied request look local)
    assert not any("X-Forwarded-For" in ln and ("header_up" in ln or "request_header" in ln)
                   for ln in _code(caddy))


def check_gb10_tls_site_hops_through_the_route_map(caddy_gb10: str) -> None:
    """18443 is refused only because its single directive hands every request to the :8080
    route map over loopback WITH X-Forwarded-For (Caddy's reverse_proxy default)."""
    code = _code(caddy_gb10)
    assert "import /etc/caddy/Caddyfile.routes" in code
    sites = [ln for ln in code if ln.startswith("https://") and ln.endswith("{")]
    assert len(sites) == 1
    body = _site(caddy_gb10, sites[0][:-2])
    assert sorted(body) == ["reverse_proxy 127.0.0.1:8080", "tls internal"], body
    assert not any("X-Forwarded-For" in ln or "header_up" in ln or "trusted_proxies" in ln for ln in code)


def check_ci(ci: str) -> None:
    for job, needles in (
        ("  compose-smoke:", ["integration/demo/fixtures/kr-edge/check_edge_block.py http://localhost:8080",
                              "exec -T proxy wget -S -O /dev/null", "HTTP/1.1 404"]),
        ("  fly-image-smoke:", ["integration/demo/fixtures/kr-edge/check_edge_block.py http://localhost:8080",
                                "docker exec estate python3", "http://127.0.0.1:8080/"]),
        ("  compose-upgrade-smoke:", ['check_edge_block.py "$BASE"',
                                      'check_edge_block.py https://localhost:18443 --cacert "$RUNNER_TEMP/caddy-root.crt"',
                                      "$COMPOSE exec -T proxy wget -S -O /dev/null", "HTTP/1.1 401"]),
    ):
        start = ci.index(job)
        nxt = re.search(r"\n  [a-z-]+:\n", ci[start + len(job):])
        body = ci[start: start + len(job) + (nxt.start() if nxt else len(ci))]
        step = body[body.index("Key rotation R2"):]
        step = step[:step.index("      - name:", 10)] if "      - name:" in step[10:] else step
        for n in needles:
            assert n in step, f"{job.strip()} R2 edge step lacks {n!r}"
        assert " -k" not in step and "--insecure" not in step


# --- the real files --------------------------------------------------------------------------


def test_the_base_route_map_refuses_the_internal_routes_except_from_loopback():
    check_edge_site(_read(CADDY_BASE))


def test_the_fly_edge_refuses_the_internal_routes_except_from_loopback():
    check_edge_site(_read(CADDY_FLY))


def test_the_gb10_tls_listener_reaches_backends_only_through_the_refusing_route_map():
    check_gb10_tls_site_hops_through_the_route_map(_read(CADDY_GB10))


def test_ci_proves_the_edge_block_on_all_three_estate_images():
    check_ci(_read(CI))
    assert CHECKER.is_file()


def test_the_ci_checker_tries_every_prefix_route_and_variant():
    import runpy

    mod = runpy.run_path(str(CHECKER))
    assert set(mod["PREFIXES"]) == {p.lstrip("/") for p in PREFIXES}
    assert {r for _, r in mod["ROUTES"]} == {r.lstrip("/") for r in ROUTES}
    assert mod["EDGE_BODY"] == EDGE_BODY


# R2 review L3: the checker's variants and its spoofed X-Forwarded-For are pinned too, not only
# its prefixes and routes (the reviewer's mutant R08, upper case dropped, survived without these).


def _checker_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kr_check_edge_block", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _expected_variants(prefix: str, route: str) -> list[str]:
    base = f"/{prefix}/{route}" if prefix else f"/{route}"
    last = route.split("/")[1]
    enc = base.replace("verify-hash", "verify%2Dhash").replace("rotation-state", "rotation%2Dstate")
    return [base, base + "/", base.upper(), enc, base + "?x=1",
            # C-32: the shapes of the C-27 real-Caddy probe (reviewer, 2026-10-28)
            base.replace("/operator/", "//operator/"), base.replace("/operator/", "/operator//"),
            base.replace("/operator/", "/%6fperator/"), base.replace("/operator/", "/operator%2F"),
            base.replace("/operator/", "/%2Foperator/"), base.replace("/operator/", "/./operator/"),
            base.replace("/operator/", "/operator/./"), base.replace("/operator/", "/x/../operator/"),
            base.replace("/operator/", "/x/%2e%2e/operator/"), base + ";x=1", base + "%00",
            base + "%20", base + "%2F", base.replace("-", "%2d"),
            base.replace("/" + last, "/" + last.title()),
            # C-1062 (reviewer C-839 P1): the CI log shows the edge's own 403 for these on every estate image
            "/" + base, "/." + base, base.replace("/operator/", "/operator%2f"), base + "."]


def test_the_ci_checker_pins_every_variant():
    mod = _checker_module()
    for prefix in mod.PREFIXES:
        for _, route in mod.ROUTES:
            got = mod._variants(prefix, route)
            assert got == _expected_variants(prefix, route)
            assert any("%2D" in v for v in got) and any(v != v.lower() for v in got)


# C-671 (reviewer C-650 F-C650-2, C-766 F-C766-3): one prefix as literal strings, so the expectation is not a copy
# of the implementation.
LEDGER_VERIFY_HASH = [
    "/ledger/operator/verify-hash", "/ledger/operator/verify-hash/", "/LEDGER/OPERATOR/VERIFY-HASH",
    "/ledger/operator/verify%2Dhash", "/ledger/operator/verify-hash?x=1", "/ledger//operator/verify-hash",
    "/ledger/operator//verify-hash", "/ledger/%6fperator/verify-hash", "/ledger/operator%2Fverify-hash",
    "/ledger/%2Foperator/verify-hash", "/ledger/./operator/verify-hash", "/ledger/operator/./verify-hash",
    "/ledger/x/../operator/verify-hash", "/ledger/x/%2e%2e/operator/verify-hash",
    "/ledger/operator/verify-hash;x=1", "/ledger/operator/verify-hash%00", "/ledger/operator/verify-hash%20",
    "/ledger/operator/verify-hash%2F", "/ledger/operator/verify%2dhash", "/ledger/operator/Verify-Hash",
    "//ledger/operator/verify-hash", "/./ledger/operator/verify-hash", "/ledger/operator%2fverify-hash",
    "/ledger/operator/verify-hash."]
# Shapes sent and reported that fail the check only on a 2xx answer: the CI log shows the service's own 404 for
# them (a harmless pass-through), so they cannot be gating until the edge refuses them.
LEDGER_VERIFY_HASH_INFO = ["/ledger/operator%252Fverify-hash", "/ledger/operator\\verify-hash"]


def test_the_variants_of_one_prefix_are_these_literal_strings():
    mod = _checker_module()
    assert mod._variants("ledger", "operator/verify-hash") == LEDGER_VERIFY_HASH
    assert len(set(LEDGER_VERIFY_HASH)) == 24


def test_the_informational_shapes_of_one_prefix_are_these_literal_strings():
    mod = _checker_module()
    assert mod._informational("ledger", "operator/verify-hash") == LEDGER_VERIFY_HASH_INFO


def test_informational_shapes_are_sent_and_reported_but_a_pass_through_does_not_fail_the_check(monkeypatch, capsys):
    mod = _checker_module()
    sent = []

    def fake_ask(url, method, secret, ctx, spoof):
        sent.append(url)
        return (403, EDGE_BODY) if url.split("edge.invalid:8080", 1)[1] not in LEDGER_VERIFY_HASH_INFO else (404, "x")

    monkeypatch.setattr(mod, "_ask", fake_ask)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    assert mod.check("http://edge.invalid:8080", None) == []
    for shape in LEDGER_VERIFY_HASH_INFO:
        assert "http://edge.invalid:8080" + shape in sent
    out = capsys.readouterr().out
    assert "info: POST /ledger/operator%252Fverify-hash: 404" in out


@pytest.mark.parametrize("status,fails", [(200, True), (204, True), (299, True), (301, False), (404, False),
                                          (500, False), (0, False)])
def test_an_informational_shape_answered_2xx_fails_the_check(monkeypatch, status, fails):
    mod = _checker_module()
    shape = "/ledger/operator\\verify-hash"

    def fake_ask(url, method, secret, ctx, spoof):
        return (status, "x") if url.endswith(shape) else (403, EDGE_BODY)

    monkeypatch.setattr(mod, "_ask", fake_ask)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    problems = mod.check("http://edge.invalid:8080", None)
    if fails:
        assert len(problems) == 1 and shape in problems[0] and str(status) in problems[0]   # only the ledger verify-hash route
    else:
        assert problems == []


def test_the_summary_line_counts_gating_requests_and_the_informational_shapes_apart(monkeypatch, capsys):
    mod = _checker_module()
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setattr(mod, "_ask", lambda url, method, secret, ctx, spoof: (
        (404, "x") if url.split("edge.invalid:8080", 1)[1] in LEDGER_VERIFY_HASH_INFO else (403, EDGE_BODY)))
    assert mod.check("http://edge.invalid:8080", None) == []
    assert capsys.readouterr().out.splitlines()[-1] == (
        "400 requests to the internal routes through http://edge.invalid:8080: 400 refused at the edge; "
        "32 informational shapes sent")


def test_the_ci_checker_sends_every_variant_and_a_spoofed_xff_with_the_secret(monkeypatch):
    mod = _checker_module()
    calls = []

    def fake_ask(url, method, secret, ctx, spoof):
        calls.append((url, method, secret, spoof))
        return 403, EDGE_BODY + "\n"

    monkeypatch.setattr(mod, "_ask", fake_ask)
    monkeypatch.setenv("FIELD_SHARED_SECRET", "tkv-fake-perimeter-not-a-secret")
    base = "http://edge.invalid:8080"
    assert mod.check(base + "/", None) == []
    want = set()
    for prefix in mod.PREFIXES:
        for method, route in mod.ROUTES:
            variants = _expected_variants(prefix, route)
            want |= {(base + v, method, False) for v in variants}
            want.add((base + variants[0], method, True))      # the spoofed XFF on the plain path
            want |= {(base + v, method, False) for v in mod._informational(prefix, route)}
    assert {(u, m, s) for u, m, _, s in calls} == want
    assert len(calls) == 8 * 2 * (25 + 2)      # the console root repeats two shapes ("//operator/..." and "/./operator/..."), so len(want) is less
    assert {sec for _, _, sec, _ in calls} == {"tkv-fake-perimeter-not-a-secret"}


# C-1062 (reviewer C-839 P2, mutants M14/M15/M17): the checker fails closed. A refused connection is status 0 (never the
# edge's 403), an HTTPError keeps its real status and body, and main() returns 1 as soon as one request is not refused.


@pytest.mark.parametrize("exc", [lambda mod: mod.urllib.error.URLError("refused"),
                                 lambda mod: ConnectionRefusedError("refused")])
def test_a_refused_connection_is_status_zero_never_the_edge_answer(monkeypatch, exc):
    mod = _checker_module()

    def boom(req, timeout, context):
        raise exc(mod)

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    status, body = mod._ask("http://edge.invalid/ledger/operator/verify-hash", "POST", None, None, False)
    assert status == 0 and body != EDGE_BODY


def test_an_http_error_keeps_its_real_status_and_body(monkeypatch):
    import io

    mod = _checker_module()

    def err(req, timeout, context):
        raise mod.urllib.error.HTTPError(req.full_url, 404, "not found", {}, io.BytesIO(b"service says no"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", err)
    assert mod._ask("http://edge.invalid/x", "GET", None, None, False) == (404, "service says no")


def test_main_exits_zero_only_when_every_request_is_refused_at_the_edge(monkeypatch, capsys):
    mod = _checker_module()
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setattr(mod, "_ask", lambda url, method, secret, ctx, spoof: (403, EDGE_BODY))
    assert mod.main(["http://edge.invalid:8080"]) == 0
    assert "::error::" not in capsys.readouterr().out
    one = "http://edge.invalid:8080/ledger/operator/verify-hash"
    monkeypatch.setattr(mod, "_ask", lambda url, method, secret, ctx, spoof: (
        (404, "service says no") if url == one and not spoof else (403, EDGE_BODY)))
    assert mod.main(["http://edge.invalid:8080"]) == 1
    out = capsys.readouterr().out
    assert out.count("::error::not refused at the edge") == 1 and "404" in out


def test_main_exits_one_when_nothing_answers_and_two_without_a_base_url(monkeypatch, capsys):
    mod = _checker_module()
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setattr(mod, "_ask", lambda url, method, secret, ctx, spoof: (0, "URLError"))
    assert mod.main(["http://edge.invalid:8080"]) == 1
    assert capsys.readouterr().out.count("::error::not refused at the edge") > 300
    assert mod.main([]) == 2


@pytest.mark.parametrize("spoof", [False, True])
def test_the_ci_checker_puts_the_spoofed_xff_and_the_secret_on_the_wire(monkeypatch, spoof):
    mod = _checker_module()
    seen = []

    class _Resp:
        status = 200

        def read(self, n):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout, context):
        seen.append(req)
        return _Resp()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    status, _ = mod._ask("http://edge.invalid/ledger/operator/rotation-state", "GET",
                         "tkv-fake-perimeter", None, spoof)
    assert status == 200 and len(seen) == 1
    req = seen[0]
    assert req.get_header("X-field-auth") == "tkv-fake-perimeter"
    assert req.get_header("X-forwarded-for") == ("127.0.0.1" if spoof else None)


@pytest.mark.parametrize("answer,spoof_only,n_problems", [
    ((200, "{}"), True, 16),                               # a spoofed XFF got through
    ((403, "Forbidden"), False, 400),                       # a 403 that is not the edge's own
    ((401, "perimeter"), False, 400),                       # the services' 401, not the edge
    ((200, EDGE_BODY), False, 432),                         # the edge's words on a 200 (and on the info shapes)
    ((404, EDGE_BODY), False, 400),                         # the edge's words on a 404
])
def test_the_ci_checker_reports_any_request_not_refused_by_the_edge(monkeypatch, answer,
                                                                    spoof_only, n_problems):
    mod = _checker_module()

    def fake_ask(url, method, secret, ctx, spoof):
        return answer if (spoof or not spoof_only) else (403, EDGE_BODY)

    monkeypatch.setattr(mod, "_ask", fake_ask)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    problems = mod.check("http://edge.invalid:8080", None)
    assert len(problems) == n_problems
    if spoof_only:
        assert all(p.endswith(repr(answer[1])) and "(spoofed XFF)" in p for p in problems)


# --- each of the eight services carries both routes -------------------------------------------


@pytest.fixture()
def _iso_env(tmp_path, monkeypatch):
    from field_core import operator_auth as oa

    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE, "FIELD_SHARED_SECRET", "FIELD_LEDGER_URL",
              "FIELD_REGISTRY_URL", "FIELD_DELEGATION_URL", "FIELD_KILLSWITCH_URL",
              "FIELD_GOVERNOR_URL", "FIELD_LEDGER_OBSERVE_EVERY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.mark.parametrize("service", sorted(APPS))
def test_each_operator_block_service_answers_verify_hash_and_rotation_state(service, _iso_env,
                                                                            monkeypatch):
    from fastapi.testclient import TestClient
    from field_core import operator_auth as oa

    key = "tkv-r2edge-key-0123456789abcdef"
    h = oa.key_sha256(key)
    reg = _iso_env / "operators.json"
    reg.write_text(json.dumps({"format": 2, "generation": 7, "operators": [
        {"operator_id": "svc-x", "status": "active", "rotation": "auto", "scopes": ["kill"],
         "key_sha256": h, "key_not_after": "2099-01-01T00:00:00Z"}]}), encoding="utf-8")
    client = TestClient(importlib.import_module(APPS[service]).create_app())
    body = json.dumps({"operator_id": "svc-x", "key_sha256": h})
    # OFF: absent
    assert client.post("/operator/verify-hash", content=body).status_code == 404
    assert client.get("/operator/rotation-state").status_code == 404
    monkeypatch.setenv(oa.ENV_REGISTRY, str(reg))
    monkeypatch.setenv("FIELD_SHARED_SECRET", "tkv-r2edge-perimeter")
    hdr = {"x-field-auth": "tkv-r2edge-perimeter"}
    assert client.post("/operator/verify-hash", content=body).status_code == 401   # perimeter
    r = client.post("/operator/verify-hash", content=body, headers=hdr)
    assert r.status_code == 200, r.text
    assert (r.json()["matched"], r.json()["matchable_now"], r.json()["registry_generation"]) == \
        ("current", True, 7)
    s = client.get("/operator/rotation-state", headers=hdr)
    assert s.status_code == 200 and s.json()["rows"][0]["current_fp"] == h[:16]
    health = client.get("/health").json()
    assert (health["operator_registry_format"], health["operator_registry_generation"]) == (2, 7)
    assert re.fullmatch(r"[0-9a-f]{16}", health["operator_roster_sha16"])
    assert "breakglass_auth_count" in health and "breakglass_attempt_count" in health
    assert h[:16] not in json.dumps(health) and h[:8] not in json.dumps(health)


# --- mutants: each must turn a check RED -------------------------------------------------------

_REMOTE = "\t\tnot remote_ip 127.0.0.0/8 ::1\n"
_XFF = "\t\theader X-Forwarded-For *\n"

MUTANTS = {
    "loopback condition dropped (base)": (CADDY_BASE, lambda t: t.replace(_REMOTE, "", 1), check_edge_site),
    "loopback condition dropped (fly)": (CADDY_FLY, lambda t: t.replace(_REMOTE, "", 1), check_edge_site),
    "forwarded matcher dropped (18443 would pass)": (
        CADDY_BASE, lambda t: t.replace("\trewrite @kr_internal_forwarded /__field_internal_route_refused\n", ""),
        check_edge_site),
    "XFF condition dropped": (CADDY_BASE, lambda t: t.replace(_XFF, "", 1), check_edge_site),
    "rotation-state not matched": (
        CADDY_BASE, lambda t: t.replace(" */operator/rotation-state*", "", 1), check_edge_site),
    "verify-hash matched only under /registry": (
        CADDY_FLY, lambda t: t.replace("path */operator/verify-hash*", "path /registry/operator/verify-hash", 1),
        check_edge_site),
    "refusal proxied instead of answered": (
        CADDY_BASE, lambda t: t.replace('respond "internal route: loopback only" 403', "reverse_proxy console:8011"),
        check_edge_site),
    "refusal answers 200": (
        CADDY_FLY, lambda t: t.replace('loopback only" 403', 'loopback only" 200'), check_edge_site),
    "fly block removed": (
        CADDY_FLY, lambda t: re.sub(r"\t@kr_internal_remote \{.*?respond [^\n]*\n\t\}\n", "", t, flags=re.S),
        check_edge_site),
    "loopback widened to everything": (
        CADDY_BASE, lambda t: t.replace("127.0.0.0/8 ::1", "0.0.0.0/0 ::/0"), check_edge_site),
    "XFF stripped on the TLS hop": (
        CADDY_GB10, lambda t: t.replace("\treverse_proxy 127.0.0.1:8080\n",
                                        "\treverse_proxy 127.0.0.1:8080 {\n\t\theader_up -X-Forwarded-For\n\t}\n"),
        check_gb10_tls_site_hops_through_the_route_map),
    "CI step dropped from fly-image-smoke": (
        CI, lambda t: t.replace("integration/demo/fixtures/kr-edge/check_edge_block.py http://localhost:8080\n"
                                "          docker exec estate", "true\n          docker exec estate"), check_ci),
    "CI 18443 check dropped": (
        CI, lambda t: t.replace('check_edge_block.py https://localhost:18443', 'true https://localhost:18443'),
        check_ci),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_turns_a_check_red(name):
    path, mutate, check = MUTANTS[name]
    original = _read(path)
    mutated = mutate(original)
    assert mutated != original, f"mutant {name!r} did not apply"
    with pytest.raises(AssertionError):
        check(mutated)
