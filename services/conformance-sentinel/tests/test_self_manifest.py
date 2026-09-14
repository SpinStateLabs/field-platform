"""S4 tests — who guards the guard, as tested properties.

Self-manifest validity + CTO ownership + read-only-grounding scope; the S3
judge budget flowing FROM the manifest (governor meters against the
manifest-derived cap); tenant isolation (structural and judge-path); and the
concrete no-self-modification properties (no mutating API surface, manifest
bytes untouched by a full check battery). OS-level filesystem immutability
stays Declared — README LIMITS."""

from fastapi.routing import APIRoute
from field_core.manifest import FieldManifest
from field_core.validation import validate_manifest_data
from spend_governor.core import SpendCapConfig

from conformance_sentinel.judge import MockJudgeClient
from conformance_sentinel.self_manifest import (
    SELF_AGENT_ID,
    load_self_manifest,
    self_manifest_path,
)
from tests.conftest import AGENT_ID, Stack, build_manifest

READ_ONLY_VERBS = ("read", "evaluate", "append", "invoke")


def test_self_manifest_validates_and_names_the_cto():
    data = load_self_manifest()
    result = validate_manifest_data(data)
    assert result.ok
    assert data["agent"]["name"] == SELF_AGENT_ID == "conformance-sentinel"
    assert "CTO" in data["identity"]["principal"]
    cap = data["enforcement"]["spend_cap"]
    assert cap and cap["on_breach"] == "halt" and cap["limit"] > 0


def test_self_manifest_scope_is_read_only_grounding():
    """Separation of duties: no scope entry grants a mutating verb — the
    Sentinel is never delegated the power to modify manifests or policy.
    The one exception is the egress ACTION `llm.messages` (v1.2 F1): the
    fixed action an enforcing gateway checks for the Sentinel's own judge
    calls — an action name, not a verb; it grants nothing beyond calling
    the model, and without it every judge call is refused `D.scope`."""
    data = load_self_manifest()
    scope = data["delegation"]["scope"]
    assert scope, "self-manifest must declare a delegation scope"
    assert "llm.messages" in scope  # F1: without it every judge call is D.scope
    for entry in scope:
        if entry == "llm.messages":
            continue
        assert entry.split()[0] in READ_ONLY_VERBS, entry


def test_judge_budget_flows_from_the_self_manifest(stack):
    """Completes the S3 spend story: the manifest's spend_cap IS the judge
    budget. Derive the cap exactly as `governor set-cap --from-manifest`
    does, apply it, and prove a judged call is allowed AND metered."""
    manifest = FieldManifest.from_dict(load_self_manifest())
    cfg = SpendCapConfig.from_manifest(manifest, SELF_AGENT_ID)
    assert cfg.limit_cents == 500  # USD 5 daily, exact cents
    r = stack.governor.put(f"/caps/{SELF_AGENT_ID}", json={
        "agent_id": SELF_AGENT_ID, "limit_cents": cfg.limit_cents,
        "period": cfg.period, "escalate_at_pct": 80})
    assert r.status_code == 200

    stack.set_cap()
    stack.sentinel.app.state.engine.judge = MockJudgeClient(rules={
        "draft the march invoices": (True, 0.95, "paraphrase")})
    token = stack.mint_token()
    v = stack.check("draft the march invoices", token_id=token)
    assert v["decision"] == "ALLOW"

    usage = stack.governor.get(f"/usage/{SELF_AGENT_ID}").json()
    assert usage["total_input_tokens"] > 0
    assert usage["total_output_tokens"] > 0


def _register_second_agent(stack, tmp_path):
    """Agent B whose manifest grants 'transfer funds' — bait for leakage."""
    path = build_manifest(tmp_path)
    other = tmp_path / "other-agent.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "read timesheets", "transfer funds").replace(
        "invoicing-agent", "other-agent")
    other.write_text(text, encoding="utf-8")
    r = stack.registry.post("/agents", json={
        "agent_id": "other-agent", "name": "Other",
        "owner": "Someone Else", "domain": "finance",
        "manifest_ref": str(other)})
    assert r.status_code in (200, 201)
    return other


def test_tenant_isolation_structural(stack, tmp_path):
    """Agent A's check never reads agent B's manifest: B's 'transfer funds'
    grant must not leak into A's verdict, and a resolver spy proves only A's
    manifest_ref was resolved during A's check."""
    stack.set_cap()
    other_ref = _register_second_agent(stack, tmp_path)

    engine = stack.sentinel.app.state.engine
    resolved: list[str] = []
    original = engine.manifests.resolve

    def spy(manifest_ref):
        resolved.append(str(manifest_ref))
        return original(manifest_ref)

    engine.manifests.resolve = spy
    try:
        # A's TOKEN even carries the action — the manifest is the envelope
        # that must refuse it, and it must be A's manifest that refuses.
        token = stack.mint_token(scope=["transfer funds"])
        v = stack.check("transfer funds", token_id=token)
    finally:
        engine.manifests.resolve = original

    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.scope"
    assert resolved, "resolver was never consulted"
    assert all(AGENT_ID in ref for ref in resolved)
    assert all(str(other_ref) != ref for ref in resolved)


def test_tenant_isolation_judge_path(stack, tmp_path):
    """With the judge on, A's judged scope contains only entries from A's own
    manifest — B's grants never reach the judge prompt."""
    stack.set_cap()
    _register_second_agent(stack, tmp_path)
    r = stack.governor.put(f"/caps/{SELF_AGENT_ID}", json={
        "agent_id": SELF_AGENT_ID, "limit_cents": 500,
        "period": "daily", "escalate_at_pct": 80})
    assert r.status_code == 200
    mock = MockJudgeClient(rules={
        "draft the march invoices": (True, 0.95, "paraphrase")})
    stack.sentinel.app.state.engine.judge = mock

    token = stack.mint_token()
    v = stack.check("draft the march invoices", token_id=token)
    assert v["decision"] == "ALLOW"

    judged = mock.calls[-1]["scope"]
    assert judged, "judge saw an empty scope"
    assert "transfer funds" not in judged
    from tests.conftest import SCOPE
    assert set(judged) <= set(SCOPE)


def test_api_surface_has_no_mutating_route():
    """The sentinel cannot modify anything over its API: no PUT/PATCH/DELETE
    anywhere, and POST exists only at /check (decision-only)."""
    from conformance_sentinel.api import create_app

    app = create_app()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        assert not (route.methods & {"PUT", "PATCH", "DELETE"}), route.path
        if "POST" in route.methods:
            assert route.path == "/check", route.path


def test_checks_leave_manifest_bytes_identical(stack):
    """Read-only grounding, concretely: a full battery of allow / block /
    judged checks leaves the agent's manifest file byte-for-byte unchanged."""
    stack.set_cap()
    r = stack.governor.put(f"/caps/{SELF_AGENT_ID}", json={
        "agent_id": SELF_AGENT_ID, "limit_cents": 500,
        "period": "daily", "escalate_at_pct": 80})
    assert r.status_code == 200
    stack.sentinel.app.state.engine.judge = MockJudgeClient(rules={
        "draft the march invoices": (True, 0.95, "paraphrase")})
    before = stack.manifest_path.read_bytes()

    token = stack.mint_token()
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    assert stack.check("transfer funds", token_id=token)["decision"] == "BLOCK"
    assert stack.check("draft the march invoices",
                       token_id=token)["decision"] == "ALLOW"

    assert stack.manifest_path.read_bytes() == before
