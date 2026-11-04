"""S4-23: GET /api/agents/{id}/manifest never 500s on a registry 200 of the wrong shape or a non-string manifest_ref.
A non-dict answer is a fixed 502; a non-string ref is the 'refused' 403 body, with no echo of the value."""
from __future__ import annotations

import pytest

from ops_console.api import ManifestRefused, guarded_manifest_path
from test_ops_console_c184 import Stub, console, dirs, sc  # noqa: F401  (dirs is a fixture)

MARK = "MADE-UP-MARKER-0123456789"


def get(dirs, body):
    mdir, _ = dirs
    return console(registry=sc(Stub(200, body)), manifest_dir=mdir).get("/api/agents/a1/manifest")


@pytest.mark.parametrize("body", [[], [1, 2], "a string", 5, True, [{"manifest_ref": "good.yaml"}]], ids=repr)
def test_a_non_dict_registry_answer_is_a_fixed_502(dirs, body):
    r = get(dirs, body)
    assert r.status_code == 502, r.text
    assert r.json() == {"detail": "registry answered an unexpected shape"}


@pytest.mark.parametrize("ref", [5, 0, True, [], {}, [MARK], {MARK: 1}, 1.5, [["a"]]], ids=repr)
def test_a_non_string_manifest_ref_is_the_refused_403_not_a_500(dirs, ref):
    r = get(dirs, {"agent_id": "a1", "manifest_ref": ref})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": {"agent_id": "a1", "ref": None, "validation": "refused",
                                   "reason": "manifest_ref is not text"}}
    assert MARK not in r.text


@pytest.mark.parametrize("ref", [None, ""])
def test_no_ref_is_still_no_ref(dirs, ref):
    r = get(dirs, {"agent_id": "a1", "manifest_ref": ref})
    assert r.status_code == 200 and r.json()["validation"] == "no_ref"


def test_a_missing_manifest_ref_key_is_no_ref(dirs):
    r = get(dirs, {"agent_id": "a1"})
    assert r.status_code == 200 and r.json()["validation"] == "no_ref"


def test_a_good_ref_still_reads(dirs):
    mdir, _ = dirs
    (mdir / "good.yaml").write_text("a: 1\n", encoding="utf-8")
    r = get(dirs, {"agent_id": "a1", "manifest_ref": "good.yaml"})
    assert r.status_code == 200 and r.json()["raw"] == "a: 1\n" and r.json()["ref"] == "good.yaml"


@pytest.mark.parametrize("ref", [5, None, [], {}, b"x"], ids=repr)
def test_the_guard_itself_refuses_a_non_string_ref(dirs, ref):
    mdir, _ = dirs
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, ref)
    assert e.value.status == 403 and e.value.reason == "manifest_ref is not text"
