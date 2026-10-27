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
