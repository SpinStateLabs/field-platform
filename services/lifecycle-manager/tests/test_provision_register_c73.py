"""provision step 2, register (C-73, reviewer C-67 and R-12): any registry answer to the register POST
other than 201 or 409 is a failed step that stops the run (fail closed), whatever the follow-up GET would
say; and the GET after a 409 is believed only when it answers 200. Real services over TestClient, as in
test_provision_unchanged_p29; the registry's HTTP client is wrapped so one answer can be forced."""

from __future__ import annotations

import pytest

from lifecycle_manager.engine import LifecycleEngine  # noqa: F401  (the unit under test)

from test_provision_unchanged_p29 import AGENT, Spy, Stack, _clean_flags, _register, stack  # noqa: F401


class Forced:
    """An HTTP answer with a body, as the registry client returns one."""

    def __init__(self, status: int, body):
        self.status_code, self._body, self.text = status, body, "forced"

    def json(self):
        return self._body


class Programmed(Spy):
    """Forwards to the real registry unless an answer is set for the POST or the GET."""

    def __init__(self, inner):
        super().__init__(inner)
        self.post_answer = None
        self.get_answer = None
        self.get_raises = None
        self.patch_answer = None
        self.calls: list[str] = []

    def post(self, *a, **kw):
        self.calls.append("POST")
        return self.post_answer if self.post_answer is not None else self.inner.post(*a, **kw)

    def get(self, *a, **kw):
        self.calls.append("GET")
        if self.get_raises is not None:
            raise self.get_raises
        return self.get_answer if self.get_answer is not None else self.inner.get(*a, **kw)

    def patch(self, url, json=None, **kw):  # noqa: A002
        self.calls.append("PATCH")
        if self.patch_answer is not None:
            self.patches.append((url, json))
            return self.patch_answer
        return super().patch(url, json=json, **kw)


@pytest.fixture()
def prog(stack):  # noqa: F811
    """A provisioned agent, then the engine's registry client replaced by a programmable one."""
    assert stack.provision().ok is True
    spy = Programmed(stack.registry)
    stack.engine.registry_http = spy
    return stack, spy


def _stored(**over):
    """What the registry would answer for the agent: the same owner and manifest_ref as the next run, so a
    caller that believed this record would report `unchanged` and send nothing."""
    return {"agent_id": AGENT, "owner": "AP Team Lead", "domain": "finance", "status": "active",
            "manifest_ref": None, **over}


# --- the register POST answers something other than 201 or 409 ----------------------------------------


@pytest.mark.parametrize("status", [200, 202, 204, 400, 401, 403, 404, 422, 500, 502, 503])
def test_a_register_answer_other_than_201_or_409_fails_the_step_and_stops_the_run(prog, status):
    stack, spy = prog
    # a follow-up GET that WOULD say "already registered, unchanged" if anything asked it
    spy.get_answer = Forced(200, _stored(manifest_ref=stack.ref_a))
    spy.post_answer = Forced(status, {"detail": "not a registration"})
    record = stack.record()
    stack.spy = spy

    report = stack.provision()

    step = _register(report)
    assert step.outcome == "failed" and step.http_status == status, step
    assert report.ok is False and report.registry_outcome is None
    assert spy.calls == ["POST"], "nothing is read or written after a failed register: " + str(spy.calls)
    assert report.token_id is None and report.cap_cents is None
    assert [s.step for s in report.steps] == ["validate", "register"]
    assert stack.record() == record


def test_an_unreachable_registry_at_the_register_post_fails_closed(prog):
    stack, spy = prog

    def boom(*a, **kw):
        raise ConnectionError("registry down")

    spy.post = boom
    report = stack.provision()
    assert _register(report).outcome == "failed" and report.ok is False and report.registry_outcome is None


# --- after a 409, the GET is believed only when it answers 200 ------------------------------------------


@pytest.mark.parametrize("status", [201, 202, 204, 301, 400, 401, 403, 404, 500, 502])
def test_a_non_200_read_after_a_409_is_not_believed_even_with_a_record_in_its_body(prog, status):
    stack, spy = prog
    spy.get_answer = Forced(status, _stored(manifest_ref=stack.ref_a))     # would match: `unchanged`
    stack.spy = spy

    report = stack.provision()

    assert report.registry_outcome == "updated", "a read that was not a 200 must fall through to the PATCH"
    assert spy.calls[:3] == ["POST", "GET", "PATCH"], spy.calls
    assert len(spy.patches) == 1


def test_a_non_200_read_never_reports_a_retired_agent_as_retired_nor_as_unchanged(prog):
    """The retired guard reads the record on a 200 only: a 500 whose body says retired is not a retirement."""
    stack, spy = prog
    spy.get_answer = Forced(500, _stored(status="retired", manifest_ref=stack.ref_a))
    report = stack.provision()
    assert report.registry_outcome == "updated" and _register(report).outcome == "ok"


def test_an_unreachable_read_after_a_409_falls_through_to_the_patch(prog):
    stack, spy = prog
    spy.get_raises = ConnectionError("registry down on the read")
    report = stack.provision()
    assert report.registry_outcome == "updated" and spy.calls[:3] == ["POST", "GET", "PATCH"]


def test_a_200_read_with_the_same_owner_and_ref_is_unchanged_and_sends_no_patch(prog):
    stack, spy = prog
    report = stack.provision()                                  # the real registry: 409, then a real 200 read
    assert report.registry_outcome == "unchanged" and spy.patches == []
    assert "PATCH" not in spy.calls


def test_a_200_read_of_a_retired_agent_stops_the_run_before_any_patch(prog):
    stack, spy = prog
    spy.get_answer = Forced(200, _stored(status="retired", manifest_ref=stack.ref_a))
    report = stack.provision()
    step = _register(report)
    assert step.outcome == "failed" and step.http_status == 409 and "retired" in step.detail
    assert spy.calls == ["POST", "GET"] and report.registry_outcome is None


# --- F-R12-2 (design, LOW): a re-provision never reconciles `domain` or `name` -----------------------------


def test_a_re_provision_with_another_domain_or_name_is_not_reconciled_today(stack):
    """Documents today's behaviour (reviewer R-12 F-R12-2): the 409 branch compares and PATCHes owner and
    manifest_ref only, so a changed `domain` is neither updated nor reported. Change this test with the
    code if domain or name ever become reconciled."""
    assert stack.provision().ok is True
    before = stack.record()
    stack.spy.patches.clear()
    again = stack.engine.provision(manifest_path=stack.manifest, owner="AP Team Lead", domain="payroll",
                                   grantor="Controller", ttl_days=30, manifest_ref=stack.ref_a, name="Renamed")
    assert again.registry_outcome == "unchanged" and stack.spy.patches == []
    assert stack.record()["domain"] == before["domain"] == "finance"
    assert stack.record()["name"] == before["name"]


# --- C-292 (reviewer C-265 F-C265-1/-2): the PATCH answer code and the unchanged step's status ------------


@pytest.mark.parametrize("status", [201, 202, 204, 301, 400, 403, 404, 409, 500, 502])
def test_a_patch_answer_other_than_200_after_a_409_fails_the_step_and_stops_the_run(prog, status):
    """Only a 200 is an updated record: a 201 or 204 from the PATCH is as refused as a 500 (mutant
    `pstatus != 200` -> `not in (200, 201)`)."""
    stack, spy = prog
    spy.patch_answer = Forced(status, {"detail": "not an update"})

    report = stack.provision(owner="Another Owner")             # a changed owner: the read cannot say unchanged

    step = _register(report)
    assert step.outcome == "failed" and step.http_status == status, step
    assert step.detail.startswith("already registered; PATCH refused"), step.detail
    assert report.ok is False and report.registry_outcome is None
    assert spy.calls == ["POST", "GET", "PATCH"], spy.calls
    assert report.token_id is None and report.cap_cents is None
    assert [s.step for s in report.steps] == ["validate", "register"]


def test_a_patch_answer_of_200_after_a_409_is_an_update_and_reports_its_status(prog):
    stack, spy = prog
    spy.patch_answer = Forced(200, {"detail": "updated"})
    report = stack.provision(owner="Another Owner")
    step = _register(report)
    assert report.registry_outcome == "updated" and step.outcome == "ok" and step.http_status == 200


def test_an_unchanged_step_reports_the_status_of_the_read_not_of_the_409(prog):
    """The register POST answered 409; the step reports the 200 of the read that proved nothing changed
    (mutant `http_status=_status(existing)` -> `status`)."""
    stack, spy = prog
    report = stack.provision()
    step = _register(report)
    assert report.registry_outcome == "unchanged" and step.outcome == "ok"
    assert step.http_status == 200, step
