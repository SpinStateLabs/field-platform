"""Key rotation slice R4a: tools/operator_rotate.py, the command line and the
HTTP estate around field_core.rotation. The HTTP estate is driven through an
httpx mock transport (no network); the command line through the fakes of the
field-core R4a tests. Probes carry the perimeter secret only, never an
operator key; the one JSON line a run prints never carries a key. Every key
and secret here is a fake test value."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO / "packages" / "field-core" / "tests"))
import operator_rotate as orot  # noqa: E402
from rotation_fakes_r4a import BUILD, ROTATOR_ID, Bed  # noqa: E402

from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402
from field_core import rotation_events as ev  # noqa: E402

FAKE_SECRET = "perimeter-test-value-not-a-secret"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    oa.reset_retired_memory()
    monkeypatch.setenv("FIELD_BUILD_SHA", BUILD)
    if os.name == "nt":
        monkeypatch.setattr(rot.os, "fsync", lambda fd: None)
    yield
    oa.reset_retired_memory()


def _config(bed: Bed, path: Path, **over) -> Path:
    cfg = {"estate": "gb10", "operators_file": str(bed.ops), "state_dir": str(bed.state),
           "rotator_id": ROTATOR_ID, "ledger_url": "http://sealed-ledger:8002",
           "services": {s: f"http://{s}:8000" for s in ev.SERVICES},
           "identities": [{"operator_id": i.operator_id, "kind": i.kind, "service": i.service,
                           "key_file": i.key_path} for i in bed.identities],
           "observer_tick_s": 60, "publish_wait_s": 60}
    cfg.update(over)
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def test_config_loads(tmp_path):
    bed = Bed(tmp_path / "e")
    settings, services, ledger = orot.load_config(_config(bed, tmp_path / "c.json"))
    assert settings.estate == "gb10" and settings.issued_by == ROTATOR_ID
    assert settings.build_sha == BUILD and len(settings.identities) == 4
    assert set(services) == set(ev.SERVICES) and ledger.startswith("http://sealed-ledger")


@pytest.mark.parametrize("over", [
    {"services": {"kill-switch": "http://k"}},                       # not all eight
    {"surprise": 1},                                                 # unknown field
    {"identities": [{"operator_id": "don-breakglass", "kind": "job", "key_file": "k"}]},
    {"identities": [{"operator_id": "svc-x", "kind": "daemon", "service": "nope",
                     "key_file": "k"}]},
    {"identities": [{"operator_id": "svc-x", "kind": "job"}]},       # no key_file
    {"unmanaged": {"not_after": "2027-02-25"}},
    {"estate": "GB10!"},
    {"ledger_url": ""},
])
def test_config_errors_are_usage(tmp_path, over, capsys):
    bed = Bed(tmp_path / "e")
    cfg = _config(bed, tmp_path / "c.json", **over)
    with pytest.raises(orot.ConfigError):
        orot.load_config(cfg)
    assert orot.main(["--config", str(cfg), "--once"], estate=bed.estate) == rot.EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["result"] == "usage"


def test_now_needs_reason_incident(tmp_path, capsys):
    bed = Bed(tmp_path / "e")
    cfg = _config(bed, tmp_path / "c.json")
    assert orot.main(["--config", str(cfg), "--now", "svc-killswitch"],
                     estate=bed.estate) == rot.EXIT_USAGE
    with pytest.raises(SystemExit):
        orot.main(["--config", str(cfg), "--once", "--dry-run"], estate=bed.estate)


# --------------------------------------------------------------------------
# the command line, against the fakes
# --------------------------------------------------------------------------

def test_once_rotates_and_prints_one_content_free_line(tmp_path, capsys):
    bed = Bed(tmp_path / "e")
    cfg = _config(bed, tmp_path / "c.json")
    assert orot.main(["--config", str(cfg), "--now", "svc-killswitch", "--reason", "incident"],
                     estate=bed.estate) == 0
    out = capsys.readouterr()
    lines = out.out.strip().splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["result"] == "completed" and summary["operator_id"] == "svc-killswitch"
    key = oa._key_from_file(bed.identity("svc-killswitch").key_path)
    for blob in (out.out, out.err):
        assert key not in blob and oa.key_sha256(key) not in blob
    assert bed.estate.of("keyrotation.started")[0]["reason"] == "incident"


def test_dry_run_and_skip_exit_codes(tmp_path, capsys):
    bed = Bed(tmp_path / "e")
    cfg = _config(bed, tmp_path / "c.json")
    before = bed.ops.read_bytes()
    assert orot.main(["--config", str(cfg), "--dry-run"], estate=bed.estate) == 0
    assert json.loads(capsys.readouterr().out)["would"] == "rotate"
    assert bed.ops.read_bytes() == before
    (bed.state / rot.FREEZE_NAME).write_text("x")
    assert orot.main(["--config", str(cfg), "--once"], estate=bed.estate) == rot.EXIT_SKIPPED


def test_an_unknown_build_sha_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FIELD_BUILD_SHA", raising=False)
    bed = Bed(tmp_path / "e")
    cfg = _config(bed, tmp_path / "c.json")
    assert orot.main(["--config", str(cfg), "--once"], estate=bed.estate) == rot.EXIT_SKIPPED
    summary = json.loads(capsys.readouterr().out)
    assert summary["skip_reason"] == "precheck" and "unknown" in summary["detail"]


# --------------------------------------------------------------------------
# the HTTP estate (mock transport; no network)
# --------------------------------------------------------------------------

class _Ledger:
    def __init__(self):
        self.appended = []

    def append(self, event_type, payload, agent_id=None):
        self.appended.append((event_type, payload))
        return {"event_type": event_type, "payload": payload}


def _http(handler, monkeypatch, secret=FAKE_SECRET):
    if secret:
        monkeypatch.setenv("FIELD_SHARED_SECRET", secret)
    else:
        monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_OPERATOR", ROTATOR_ID)
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "fok_test-rotator-not-a-real-key")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    services = {s: f"http://{s}:8000" for s in ev.SERVICES}
    ledger = _Ledger()
    return orot.HttpEstate(services, "http://sealed-ledger:8002", client=client,
                           ledger=ledger), ledger


def test_probes_carry_the_perimeter_secret_and_never_an_operator_key(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path == "/operator/verify-hash":
            return httpx.Response(200, json={"operator_id": "svc-killswitch", "matched": "next",
                                             "matchable_now": True, "retired": False})
        if request.url.path == "/operator/rotation-state":
            return httpx.Response(200, json={"identity_key_fp": "a" * 16})
        if request.url.path == "/health":
            return httpx.Response(200, json={"build_sha": BUILD})
        return httpx.Response(404)
    est, _ = _http(handler, monkeypatch)
    assert est.verify_hash("kill-switch", "svc-killswitch", "b" * 64)["matched"] == "next"
    assert est.rotation_state("kill-switch")["identity_key_fp"] == "a" * 16
    assert est.build_sha("kill-switch") == BUILD
    for r in seen:
        assert r.headers.get("x-field-auth") == FAKE_SECRET
        assert "x-field-operator" not in r.headers and "x-field-operator-key" not in r.headers
    body = json.loads(seen[0].content)
    assert body == {"operator_id": "svc-killswitch", "key_sha256": "b" * 64}
    assert seen[0].method == "POST" and str(seen[0].url).startswith("http://kill-switch:8000/")


@pytest.mark.parametrize("status", [401, 403, 404, 503])
def test_a_non_200_answer_is_an_estate_error(monkeypatch, status):
    est, _ = _http(lambda r: httpx.Response(status, json={"detail": "x"}), monkeypatch)
    with pytest.raises(rot.EstateError):
        est.verify_hash("kill-switch", "svc-killswitch", "b" * 64)
    with pytest.raises(rot.EstateError):
        est.rotation_state("kill-switch")


def test_a_transport_error_is_an_estate_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down")
    est, _ = _http(handler, monkeypatch)
    with pytest.raises(rot.EstateError):
        est.build_sha("kill-switch")


def test_refusals_count_both_types_naming_the_id_since_the_soak(monkeypatch):
    asked = []

    def handler(request: httpx.Request):
        asked.append(dict(request.url.params))
        rows = [{"payload": {"claimed_id": "svc-killswitch"}},
                {"payload": {"claimed_id": "svc-registry"}},
                {"payload": {"operator_claimed": "svc-killswitch"}}]
        return httpx.Response(200, json=rows)
    est, _ = _http(handler, monkeypatch)
    assert est.refusals("svc-killswitch", oa.parse_time("2026-11-20T03:00:00Z")) == 4
    assert {a["event_type"] for a in asked} == set(orot.REFUSAL_TYPES)
    assert all(a["since"] == "2026-11-20T03:00:00Z" for a in asked)


def test_appends_go_through_the_ledger_client(monkeypatch):
    est, ledger = _http(lambda r: httpx.Response(404), monkeypatch)
    est.append("keyrotation.skipped", {"operator_id": None, "estate": "gb10", "run_id": "r1",
                                       "skip_reason": "lock"})
    assert ledger.appended[0][0] == "keyrotation.skipped"

    class Down:
        def append(self, *a, **kw):
            raise RuntimeError("ledger append returned 503")
    est._ledger = Down()
    with pytest.raises(rot.EstateError):
        est.append("keyrotation.skipped", {})


def test_without_a_perimeter_secret_no_auth_header_is_sent(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"build_sha": BUILD})
    est, _ = _http(handler, monkeypatch, secret=None)
    est.build_sha("kill-switch")
    assert "x-field-auth" not in seen[0].headers
