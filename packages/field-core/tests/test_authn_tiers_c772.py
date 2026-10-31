"""Per-tier perimeter keys (C-772, Don ruling D5 2026-10-30; platform half of MCP constraint 2).

A read key is accepted only on a safe method (GET, HEAD, OPTIONS) of a path not listed as write-only; a request that
changes anything needs the full key (FIELD_SHARED_SECRET). A read key never authorises a write, whatever the route.
Every key here is a FAKE value."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from field_core import authn
from field_core.authn import ENV_VAR, HEADER, install

FULL = "full-key-demo-only-0001"
READ = "read-key-demo-only-0002"
SPECIFIC = "registry-read-key-demo-0003"
OTHER = "other-read-key-demo-only-0004"
READ_ENV = "FIELD_READ_KEY"
REGISTRY_ENV = "FIELD_READ_KEY_AGENT_REGISTRY"
ALL_KEYS = (FULL, READ, SPECIFIC, OTHER)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in (ENV_VAR, READ_ENV, REGISTRY_ENV, "FIELD_READ_KEY_OTHER_SERVICE"):
        monkeypatch.delenv(k, raising=False)


def make_app(**kw) -> TestClient:
    app = FastAPI()
    install(app, **kw)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/data")
    def data():
        return {"value": 42}

    @app.get("/danger")
    def danger():          # a GET that changes something: only the write key may call it
        return {"changed": True}

    @app.post("/data")
    def post_data():
        return {"written": True}

    @app.put("/data")
    def put_data():
        return {"written": True}

    @app.patch("/data")
    def patch_data():
        return {"written": True}

    @app.delete("/data")
    def delete_data():
        return {"written": True}

    return TestClient(app)


# ------------------------------------------------------------ the full key alone: unchanged behaviour

def test_with_only_the_full_key_set_nothing_changes(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    c = make_app()
    assert c.get("/data").status_code == 401 and c.post("/data").status_code == 401
    assert c.get("/data", headers={HEADER: FULL}).status_code == 200
    assert c.post("/data", headers={HEADER: FULL}).status_code == 200


# ------------------------------------------------------------ the read key

def test_a_read_key_reads_and_never_writes(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    h = {HEADER: READ}
    assert c.get("/data", headers=h).status_code == 200
    assert c.head("/data", headers=h).status_code in (200, 405)       # HEAD is a safe method: never a 401
    assert c.head("/data", headers=h).status_code != 401
    for call in (c.post, c.put, c.patch, c.delete):
        assert call("/data", headers=h).status_code == 401, call.__name__


def test_the_full_key_still_does_everything(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    h = {HEADER: FULL}
    assert c.get("/data", headers=h).status_code == 200
    for call in (c.post, c.put, c.patch, c.delete):
        assert call("/data", headers=h).status_code == 200, call.__name__


def test_a_wrong_or_empty_key_is_refused_with_the_set_up_of_both_keys(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    assert c.get("/data").status_code == 401
    assert c.get("/data", headers={HEADER: ""}).status_code == 401
    assert c.get("/data", headers={HEADER: "wrong"}).status_code == 401
    assert c.get("/data", headers={HEADER: READ + "x"}).status_code == 401


def test_an_empty_read_key_variable_is_no_key(monkeypatch):
    """A blank FIELD_READ_KEY must not make the empty header a valid key."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, "")
    c = make_app()
    assert c.get("/data", headers={HEADER: ""}).status_code == 401
    assert c.get("/data").status_code == 401


def test_health_and_open_paths_stay_open_with_both_keys(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app(open_paths={"/data"})
    assert c.get("/health").status_code == 200
    assert c.get("/data").status_code == 200


def test_a_get_listed_as_write_only_needs_the_full_key(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app(write_only_paths={"/danger"})
    assert c.get("/danger", headers={HEADER: READ}).status_code == 401
    assert c.get("/danger", headers={HEADER: FULL}).status_code == 200
    assert c.get("/data", headers={HEADER: READ}).status_code == 200


# ------------------------------------------------------------ fail closed

def test_a_read_key_without_a_full_key_still_refuses_every_write(monkeypatch):
    """No FIELD_SHARED_SECRET must not turn a configured read key into an open write path."""
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    assert c.get("/data", headers={HEADER: READ}).status_code == 200
    assert c.get("/data").status_code == 401
    for call in (c.post, c.put, c.patch, c.delete):
        assert call("/data", headers={HEADER: READ}).status_code == 401, call.__name__
        assert call("/data").status_code == 401, call.__name__


def test_install_refuses_a_read_key_equal_to_the_full_key(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, FULL)
    with pytest.raises(authn.TierKeyError):
        install(FastAPI())


def test_a_read_key_set_equal_to_the_full_key_after_install_adds_no_power(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    monkeypatch.setenv(READ_ENV, FULL)
    assert authn.tier_key_problem() is not None
    assert c.post("/data", headers={HEADER: READ}).status_code == 401


# ------------------------------------------------------------ one key per service

def test_a_service_key_is_used_for_that_service_and_the_generic_one_is_not_a_fallback(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    monkeypatch.setenv(REGISTRY_ENV, SPECIFIC)
    c = make_app(service="agent-registry")
    assert c.get("/data", headers={HEADER: SPECIFIC}).status_code == 200
    assert c.get("/data", headers={HEADER: READ}).status_code == 401     # generic key is not accepted here
    assert c.post("/data", headers={HEADER: SPECIFIC}).status_code == 401


def test_a_service_without_its_own_key_uses_the_generic_one(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    monkeypatch.setenv(REGISTRY_ENV, SPECIFIC)
    c = make_app(service="other-service")
    assert c.get("/data", headers={HEADER: READ}).status_code == 200
    assert c.get("/data", headers={HEADER: SPECIFIC}).status_code == 401  # another service's key


def test_a_service_key_equal_to_the_full_key_is_refused_at_install(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(REGISTRY_ENV, FULL)
    with pytest.raises(authn.TierKeyError):
        install(FastAPI(), service="agent-registry")


# ------------------------------------------------------------ the keys never leave

def test_no_refusal_and_no_log_line_carries_a_key(monkeypatch, caplog):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    monkeypatch.setenv(REGISTRY_ENV, SPECIFIC)
    caplog.set_level(logging.DEBUG)
    c = make_app(service="agent-registry")
    bodies = []
    for h in ({HEADER: OTHER}, {HEADER: SPECIFIC}, {HEADER: FULL + "x"}, {}):
        for call in (c.get, c.post):
            r = call("/data", headers=h)
            bodies.append(r.text + str(dict(r.headers)))
    text = "\n".join(bodies) + caplog.text
    for key in ALL_KEYS:
        for i in range(0, len(key) - 7):
            assert key[i:i + 8] not in text, f"a key slice leaked: {key[:4]}..{i}"


def test_the_refusal_text_is_the_same_for_a_valid_read_key_on_a_write_and_for_no_key(monkeypatch):
    """A read key refused on a write must not tell the caller it was a valid read key."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = make_app()
    a = c.post("/data", headers={HEADER: READ})
    b = c.post("/data", headers={HEADER: "nope"})
    assert (a.status_code, a.json()) == (b.status_code, b.json())


def test_read_auth_headers_carry_only_the_read_key(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    monkeypatch.setenv("FIELD_OPERATOR", "op1")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "fok_" + "A" * 43)
    assert authn.read_auth_headers() == {HEADER: READ}
    assert authn.read_auth_headers("agent-registry") == {HEADER: READ}
    monkeypatch.setenv(REGISTRY_ENV, SPECIFIC)
    assert authn.read_auth_headers("agent-registry") == {HEADER: SPECIFIC}
    monkeypatch.delenv(READ_ENV)
    monkeypatch.delenv(REGISTRY_ENV)
    assert authn.read_auth_headers() == {}


def test_authn_source_never_logs_or_prints():
    import inspect
    src = inspect.getsource(authn)
    for word in ("logging", "print(", "logger", "log."):
        assert word not in src, word


# ------------------------------------------------------------ review C-783 (F-C783-1, -2, -4)

class _Prefixed:
    """What a server that keeps the proxy prefix sends: scope path WITH the prefix, root_path set."""

    def __init__(self, app, prefix="/api"):
        self.app, self.prefix = app, prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope, path=self.prefix + scope["path"], root_path=self.prefix)
        await self.app(scope, receive, send)


def _app_with(extra_routes=(), **kw) -> FastAPI:
    app = FastAPI()
    install(app, **kw)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/w")
    def w():
        return {"changed": True}

    @app.get("/items/{i}")
    def item(i: str):
        return {"changed": i}

    @app.get("/data")
    def data():
        return {"value": 42}

    @app.options("/data")
    def options_data():
        return {"ok": True}

    return app


def test_a_write_only_path_still_holds_behind_a_root_path_prefix(monkeypatch):
    """F-C783-1: matching request.url.path alone fails OPEN when the server keeps the prefix in scope["path"]."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_Prefixed(_app_with(write_only_paths={"/w"})))
    assert c.get("/w", headers={HEADER: READ}).status_code == 401
    assert c.get("/w", headers={HEADER: FULL}).status_code == 200
    assert c.get("/data", headers={HEADER: READ}).status_code == 200


def test_a_write_only_path_matches_a_trailing_slash_spelling(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_app_with(write_only_paths={"/w"}), follow_redirects=False)
    assert c.get("/w/", headers={HEADER: READ}).status_code == 401
    c2 = TestClient(_app_with(write_only_paths={"/w/"}), follow_redirects=False)
    assert c2.get("/w", headers={HEADER: READ}).status_code == 401


def test_a_write_only_path_may_be_a_template(monkeypatch):
    """F-C783-2: twelve GET routes carry a path parameter; a listing that cannot name them protects none."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_app_with(write_only_paths={"/items/{i}"}))
    assert c.get("/items/a", headers={HEADER: READ}).status_code == 401
    assert c.get("/items/a", headers={HEADER: FULL}).status_code == 200
    assert c.get("/data", headers={HEADER: READ}).status_code == 200


def test_the_install_error_text_never_holds_a_key(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, FULL)
    with pytest.raises(authn.TierKeyError) as exc:
        install(FastAPI())
    text = str(exc.value) + repr(exc.value.args)
    for i in range(0, len(FULL) - 7):
        assert FULL[i:i + 8] not in text


def test_keys_are_compared_in_constant_time(monkeypatch):
    """A behavioural test cannot see timing; pin that every comparison goes through hmac.compare_digest."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    calls = []
    real = authn.hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(authn.hmac, "compare_digest", spy)
    c = TestClient(_app_with())
    n = len(calls)                       # install compared the two keys once
    assert n >= 1
    c.get("/data", headers={HEADER: FULL})
    assert len(calls) > n
    n = len(calls)
    c.get("/data", headers={HEADER: READ})
    assert len(calls) >= n + 2           # the full key first, then the read key


def test_options_is_a_safe_method_and_trace_is_not(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_app_with())
    assert c.options("/data", headers={HEADER: READ}).status_code == 200
    assert c.request("TRACE", "/data", headers={HEADER: READ}).status_code == 401


def test_a_blank_service_key_variable_is_unset_so_the_generic_key_applies(monkeypatch):
    """F-C783-4(d): pinned. A blank FIELD_READ_KEY_<SERVICE> does not disable the tier for that service."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    monkeypatch.setenv(REGISTRY_ENV, "")
    c = TestClient(_app_with(service="agent-registry"))
    assert c.get("/data", headers={HEADER: READ}).status_code == 200
    assert c.get("/data", headers={HEADER: ""}).status_code == 401


# ------------------------------------------------------------ review C-795 pins (F-C795-1, -2, -3)

def _files_app(**kw) -> FastAPI:
    app = FastAPI()
    install(app, **kw)

    @app.get("/files/{p:path}")
    def files(p: str):
        return {"changed": p}

    @app.get("/a.b/{x}")
    def ab(x: str):
        return {"x": x}

    @app.get("/a.b/{x}/more")
    def abmore(x: str):
        return {"x": x}

    @app.get("/aXb/{x}")
    def axb(x: str):
        return {"x": x}

    @app.get("/v{n}/files/{p:path}")
    def vfiles(n: str, p: str):
        return {"n": n, "p": p}

    @app.get("/v{n}/w")
    def vn(n: str):
        return {"n": n}

    return app


def test_a_path_template_with_a_path_converter_spans_slashes(monkeypatch):
    """F-C795-1: `{p:path}` must match a multi-segment value; a single-segment match leaves it open to a read key."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_files_app(write_only_paths={"/files/{p:path}"}))
    assert c.get("/files/a/b/c", headers={HEADER: READ}).status_code == 401
    assert c.get("/files/a", headers={HEADER: READ}).status_code == 401
    assert c.get("/files/a/b/c", headers={HEADER: FULL}).status_code == 200


def test_a_plain_template_does_not_span_slashes_and_literal_parts_are_escaped(monkeypatch):
    """F-C795-2: a `.` in a listed path is a dot, not any character; `{x}` is one segment."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_files_app(write_only_paths={"/a.b/{x}", "/v{n}/w"}))
    assert c.get("/a.b/1", headers={HEADER: READ}).status_code == 401
    assert c.get("/aXb/1", headers={HEADER: READ}).status_code == 200          # a look-alike is not blocked
    assert c.get("/v1/w", headers={HEADER: READ}).status_code == 401           # a template inside a segment
    c2 = TestClient(_files_app(write_only_paths={"/a.b/{x}"}))
    assert c2.get("/a.b/1/more", headers={HEADER: READ}).status_code == 200    # {x} is one segment, not a prefix
    assert c2.get("/files/a/b/c", headers={HEADER: READ}).status_code == 200   # unlisted stays readable


def test_an_open_path_is_matched_on_the_request_path_so_a_prefix_fails_closed(monkeypatch):
    """F-C795-3: behind a root_path prefix `/api/health` is not `/health`: authn applies (fail closed)."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_Prefixed(_app_with()))
    assert c.get("/health").status_code == 401
    assert c.get("/health", headers={HEADER: READ}).status_code == 200


# ------------------------------------------------------------ review C-859: a read key never reaches the operator internals

def test_a_read_key_never_reaches_the_two_internal_operator_routes(monkeypatch):
    """The routes are listed write-only by default, with no adopter action: rotation-state is a GET."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    app = FastAPI()
    install(app)

    @app.get("/operator/rotation-state")
    def state():
        return {"rotation": "state"}

    @app.post("/operator/verify-hash")
    def verify():
        return {"matched": "none"}

    c = TestClient(app)
    assert c.get("/operator/rotation-state", headers={HEADER: READ}).status_code == 401
    assert c.get("/operator/rotation-state", headers={HEADER: FULL}).status_code == 200
    assert c.post("/operator/verify-hash", headers={HEADER: READ}).status_code == 401


def test_the_real_operator_health_routes_refuse_a_read_key(monkeypatch, tmp_path):
    """Combined: authn tiers plus the real operator_health routes, operator layer armed."""
    import json
    from field_core import operator_auth as oa
    from field_core import operator_health as oh
    p = tmp_path / "operators.json"
    p.write_bytes(json.dumps({"format": 1, "operators": []}).encode())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    app = FastAPI()
    install(app)
    oh.install(app, ledger_getter=lambda a: None)
    c = TestClient(app)
    assert c.get(oh.ROTATION_STATE_PATH, headers={HEADER: FULL}).status_code == 200
    assert c.get(oh.ROTATION_STATE_PATH, headers={HEADER: READ}).status_code == 401


def test_the_internal_path_list_is_the_operator_health_route_constants():
    """C-971 / C-887: authn keeps its own literal list of the two internal routes; it must equal the route constants
    so a rename or an added internal route cannot silently leave a read key a way in."""
    from field_core import operator_health as oh
    assert authn.INTERNAL_PATHS == frozenset({oh.VERIFY_HASH_PATH, oh.ROTATION_STATE_PATH})


# ------------------------------------------------------------ review C-43 (F-C369-1): the empty path capture

def test_a_path_template_also_matches_its_empty_capture(monkeypatch):
    """Starlette's `path` convertor accepts the empty string, so GET /files/ is a route hit with p="". Normalised it is
    /files, which `/files/.+` does not match: the read key reached the handler."""
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_files_app(write_only_paths={"/files/{p:path}"}), follow_redirects=False)
    for spelling in ("/files/", "/files", "/files//"):
        r = c.get(spelling, headers={HEADER: READ})
        assert r.status_code == 401, (spelling, r.status_code)
    assert c.get("/files/a/b/c", headers={HEADER: READ}).status_code == 401
    assert c.get("/files/a/b/c", headers={HEADER: FULL}).status_code == 200


def test_an_empty_capture_of_a_nested_template_is_covered_and_an_unrelated_path_is_not(monkeypatch):
    monkeypatch.setenv(ENV_VAR, FULL)
    monkeypatch.setenv(READ_ENV, READ)
    c = TestClient(_files_app(write_only_paths={"/v{n}/files/{p:path}"}), follow_redirects=False)
    assert c.get("/v1/files/", headers={HEADER: READ}).status_code == 401
    assert c.get("/v1/files/x/y", headers={HEADER: READ}).status_code == 401
    assert c.get("/a.b/1", headers={HEADER: READ}).status_code == 200
